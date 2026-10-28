from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.core import signing
from django.db.models import Q
from django.utils import timezone

from catalog.models import Product, ProductVariant
from storefront.models import ShippingRate, StoreSettings

from .models import Cart


class PricingError(ValueError):
    pass


class QuoteChanged(PricingError):
    pass


@dataclass(frozen=True)
class PricedLine:
    cart_item: object
    cart_item_id: int
    product: Product
    variant: ProductVariant | None
    quantity: int
    regular_unit_toman: int
    sale_unit_toman: int
    item_discount_toman: int
    line_total_toman: int


@dataclass(frozen=True)
class CartQuote:
    lines: tuple
    subtotal_toman: int
    item_discount_toman: int
    coupon_discount_toman: int
    shipping_toman: int
    shipping_label: str
    tax_rate_percent: Decimal
    taxable_base_toman: int
    tax_toman: int
    total_toman: int
    coupon: object = None

    @property
    def discount_total_toman(self):
        return self.item_discount_toman + self.coupon_discount_toman


def _round_toman(amount):
    return int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _line_prices(product, variant):
    if product.is_digital:
        variant = None
    if product.status != Product.Status.PUBLISHED:
        raise PricingError(f"«{product.name}» دیگر برای فروش در دسترس نیست.")
    if variant and (variant.product_id != product.pk or not variant.is_active):
        raise PricingError("گونهٔ انتخاب‌شده در دسترس نیست.")
    if not product.is_digital and product.variants.filter(is_active=True).exists() and not variant:
        raise PricingError(f"برای «{product.name}» یک گونه انتخاب کنید.")
    if product.is_free:
        return 0, 0
    regular = variant.regular_price_toman if variant else product.price_toman
    sale = variant.sale_override_toman if variant and variant.sale_override_toman is not None else product.sale_price_toman
    if sale is not None and sale >= regular:
        raise PricingError(f"قیمت محصول «{product.name}» نیازمند بررسی فروشگاه است.")
    return regular, sale if sale is not None else regular


def _category_ids(category):
    result = set()
    while category is not None and category.pk not in result:
        result.add(category.pk)
        category = category.parent
    return result


def _coupon_discount(coupon, user, lines, eligible_total):
    if coupon is None:
        return 0
    now = timezone.now()
    if not coupon.is_active or (coupon.starts_at and now < coupon.starts_at) or (coupon.ends_at and now >= coupon.ends_at):
        raise PricingError("کد تخفیف فعال نیست یا مهلت آن پایان یافته است.")
    if eligible_total < coupon.minimum_purchase_toman:
        raise PricingError("مبلغ سبد برای استفاده از این کد کافی نیست.")
    uses = coupon.redemptions.exclude(status="cancelled")
    if coupon.usage_limit is not None and uses.count() >= coupon.usage_limit:
        raise PricingError("ظرفیت استفاده از این کد تکمیل شده است.")
    if uses.filter(user=user).count() >= coupon.per_customer_limit:
        raise PricingError("سقف استفادهٔ این کد برای حساب شما تکمیل شده است.")
    if coupon.discount_type == coupon.DiscountType.PERCENT:
        discount = _round_toman(Decimal(eligible_total) * coupon.value / Decimal("100"))
    else:
        discount = min(eligible_total, int(coupon.value))
    if coupon.maximum_discount_toman is not None:
        discount = min(discount, coupon.maximum_discount_toman)
    return min(discount, eligible_total)


def _shipping_quote(settings_obj, address, payable_items):
    province = address.province if address else ""
    city = address.city if address else ""
    rates = list(ShippingRate.objects.filter(is_enabled=True).filter(
        (Q(province="") | Q(province=province)) & (Q(city="") | Q(city=city))
    ))
    rates.sort(key=lambda row: (bool(row.province), bool(row.city), -row.position), reverse=True)
    if rates:
        rate = rates[0]
        charge, threshold, label = rate.charge_toman, rate.free_threshold_toman, rate.name
    else:
        charge = settings_obj.default_shipping_toman
        threshold = settings_obj.free_shipping_threshold_toman
        label = "پست ایران"
    if threshold is not None and payable_items >= threshold:
        charge = 0
    return charge, label


def build_quote(cart: Cart, user, address=None, coupon_code=""):
    items = list(cart.items.select_related("product", "variant", "product__category").order_by("id"))
    if not items:
        raise PricingError("سبد خرید خالی است.")
    settings_obj = StoreSettings.get_solo()
    lines = []
    subtotal = item_discount = sale_total = 0
    eligible_total = 0
    coupon = None
    if coupon_code:
        from .models import Coupon
        coupon = Coupon.objects.filter(code__iexact=coupon_code.strip()).first()
        if coupon is None:
            raise PricingError("کد تخفیف معتبر نیست.")
        products_allowed = set(coupon.eligible_products.values_list("pk", flat=True))
        categories_allowed = set(coupon.eligible_categories.values_list("pk", flat=True))
    else:
        products_allowed, categories_allowed = set(), set()
    for item in items:
        product, variant, quantity = item.product, item.variant, item.quantity
        regular, sale = _line_prices(product, variant)
        if product.is_digital:
            if not product.assets.filter(is_active=True).exists():
                raise PricingError(f"فایل «{product.name}» هنوز آماده نیست.")
            stock = 1
        else:
            stock = variant.stock_quantity if variant else product.stock_quantity
        if product.is_digital and quantity != 1:
            raise PricingError("هر محصول دیجیتال یک‌بار قابل خرید است.")
        if stock < quantity:
            raise PricingError(f"موجودی «{product.name}» برای تعداد انتخاب‌شده کافی نیست.")
        base = regular * quantity
        line_sale = sale * quantity
        line_discount = base - line_sale
        subtotal += base
        item_discount += line_discount
        sale_total += line_sale
        category_ids = _category_ids(product.category)
        coupon_unrestricted = not products_allowed and not categories_allowed
        if coupon_unrestricted or product.pk in products_allowed or category_ids.intersection(categories_allowed):
            eligible_total += line_sale
        lines.append(PricedLine(item, item.pk, product, variant, quantity, regular, sale, line_discount, line_sale))
    coupon_discount = _coupon_discount(coupon, user, lines, eligible_total)
    if all(line.product.is_digital for line in lines):
        shipping, shipping_label = 0, "تحویل دیجیتال"
    else:
        shipping, shipping_label = _shipping_quote(settings_obj, address, sale_total - coupon_discount)
    rate = settings_obj.tax_rate_percent if settings_obj.tax_enabled else Decimal("0")
    taxable = max(0, sale_total - coupon_discount + (shipping if settings_obj.shipping_is_taxable else 0))
    tax = _round_toman(Decimal(taxable) * rate / Decimal("100"))
    total = sale_total - coupon_discount + shipping + tax
    return CartQuote(tuple(lines), subtotal, item_discount, coupon_discount, shipping, shipping_label, rate, taxable, tax, total, coupon)


def quote_payload(user, cart, address, coupon_code, quote):
    return {
        "user": user.pk,
        "cart": cart.pk,
        "address": address.pk if address else None,
        "address_updated": address.updated_at.isoformat() if address else None,
        "coupon": (coupon_code or "").strip().upper(),
        "lines": [[line.cart_item_id, line.product.pk, line.variant.pk if line.variant else None, line.quantity,
                   line.regular_unit_toman, line.sale_unit_toman] for line in quote.lines],
        "subtotal": quote.subtotal_toman,
        "item_discount": quote.item_discount_toman,
        "coupon_discount": quote.coupon_discount_toman,
        "shipping": quote.shipping_toman,
        "shipping_label": quote.shipping_label,
        "tax_rate": str(quote.tax_rate_percent),
        "tax": quote.tax_toman,
        "total": quote.total_toman,
    }


def sign_quote(user, cart, address, coupon_code, quote):
    return signing.dumps(quote_payload(user, cart, address, coupon_code, quote), salt="astrostore.checkout.quote.v1")


def verify_quote(token, user, cart, address, coupon_code, quote):
    try:
        supplied = signing.loads(token, salt="astrostore.checkout.quote.v1", max_age=900)
    except signing.BadSignature as exc:
        raise QuoteChanged("خلاصهٔ قیمت منقضی یا نامعتبر است.") from exc
    if supplied != quote_payload(user, cart, address, coupon_code, quote):
        raise QuoteChanged("قیمت یا موجودی تغییر کرده است؛ خلاصهٔ تازه را بررسی و دوباره تأیید کنید.")
