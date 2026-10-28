import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import InventoryMovement, Product, ProductVariant
from storefront.models import AuditLog

from .models import Cart, CartItem, Coupon, CouponRedemption, Order, OrderEvent, OrderItem, WishlistItem
from .pricing import PricingError, build_quote, verify_quote


class StockError(PricingError):
    pass


def _guest_token(request):
    token = request.session.get("guest_cart_token")
    try:
        return uuid.UUID(str(token))
    except (TypeError, ValueError, AttributeError):
        token = uuid.uuid4()
        request.session["guest_cart_token"] = str(token)
        return token


def merge_guest_cart(request, user):
    raw_token = request.session.get("guest_cart_token")
    if not raw_token:
        return None
    try:
        token = uuid.UUID(str(raw_token))
    except (TypeError, ValueError, AttributeError):
        request.session.pop("guest_cart_token", None)
        return None
    with transaction.atomic():
        guest = Cart.objects.select_for_update().filter(guest_token=token).first()
        if guest is None:
            request.session.pop("guest_cart_token", None)
            return None
        user_cart = Cart.objects.select_for_update().filter(user=user).first()
        if user_cart is None:
            guest.user = user
            guest.guest_token = None
            guest.save(update_fields=("user", "guest_token", "updated_at"))
            request.session.pop("guest_cart_token", None)
            return guest
        for item in guest.items.select_for_update().select_related("product", "variant").order_by("pk"):
            existing = user_cart.items.filter(product=item.product, variant=item.variant).first()
            stock = 1 if item.product.is_digital else (item.variant.stock_quantity if item.variant else item.product.stock_quantity)
            if item.product.status != Product.Status.PUBLISHED or stock < 1:
                continue
            target = min(stock, item.quantity + (existing.quantity if existing else 0))
            if existing:
                existing.quantity = target
                existing.save(update_fields=("quantity", "updated_at"))
            else:
                item.cart = user_cart
                item.quantity = min(item.quantity, stock)
                item.save(update_fields=("cart", "quantity", "updated_at"))
        guest.delete()
        request.session.pop("guest_cart_token", None)
        return user_cart


def get_cart(request):
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if request.session.get("guest_cart_token"):
            cart = merge_guest_cart(request, request.user) or cart
        if cart is None:
            cart = Cart.objects.create(user=request.user)
        return cart
    token = _guest_token(request)
    cart, _ = Cart.objects.get_or_create(guest_token=token)
    return cart


def _stock(product, variant):
    if product.is_digital:
        if not product.assets.filter(is_active=True).exists():
            raise StockError("فایل این محصول هنوز آماده نیست.")
        return 1
    if variant:
        if variant.product_id != product.pk or not variant.is_active:
            raise StockError("گونهٔ انتخاب‌شده در دسترس نیست.")
        return variant.stock_quantity
    if product.variants.filter(is_active=True).exists():
        raise StockError("برای این محصول یک گونه انتخاب کنید.")
    return product.stock_quantity


def add_to_cart(cart, product, variant=None, quantity=1):
    if product.status != Product.Status.PUBLISHED:
        raise StockError("این محصول برای فروش در دسترس نیست.")
    if not isinstance(quantity, int) or quantity < 1 or quantity > 99:
        raise StockError("تعداد انتخاب‌شده معتبر نیست.")
    if product.is_free:
        raise StockError("محصول رایگان را مستقیم از صفحهٔ محصول دانلود کنید.")
    if product.is_digital:
        variant = None
        if CartItem.objects.filter(cart=cart, product=product).exists():
            raise StockError("این محصول دیجیتال قبلاً در سبد شما هست.")
        quantity = 1
    stock = _stock(product, variant)
    if stock < 1:
        raise StockError("این کالا موجود نیست.")
    try:
        with transaction.atomic():
            item = CartItem.objects.select_for_update().filter(cart=cart, product=product, variant=variant).first()
            total = quantity + (item.quantity if item else 0)
            if total > stock:
                raise StockError("تعداد انتخاب‌شده از موجودی بیشتر است.")
            if item:
                item.quantity = total
                item.save(update_fields=("quantity", "updated_at"))
            else:
                item = CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=quantity)
            return item
    except IntegrityError:
        item = CartItem.objects.get(cart=cart, product=product, variant=variant)
        if item.quantity + quantity > stock:
            raise StockError("تعداد انتخاب‌شده از موجودی بیشتر است.")
        item.quantity += quantity
        item.save(update_fields=("quantity", "updated_at"))
        return item


def update_cart_item(cart, item_id, quantity):
    with transaction.atomic():
        item = CartItem.objects.select_for_update().select_related("product", "variant").get(pk=item_id, cart=cart)
        if quantity <= 0:
            item.delete()
            return None
        if item.product.is_digital and quantity > 1:
            raise StockError("هر محصول دیجیتال یک‌بار در سبد قرار می‌گیرد.")
        if quantity > 99 or quantity > _stock(item.product, item.variant):
            raise StockError("تعداد انتخاب‌شده از موجودی بیشتر است.")
        item.quantity = quantity
        item.save(update_fields=("quantity", "updated_at"))
        return item


def _new_order_number():
    return f"AS{timezone.localdate().strftime('%y%m%d')}{secrets.token_hex(4).upper()}"


def create_checkout_order(*, cart, user, address, coupon_code, checkout_key, quote_token):
    if address is not None and address.user_id != user.pk:
        raise PricingError("نشانی انتخاب‌شده متعلق به این حساب نیست.")
    with transaction.atomic():
        existing = Order.objects.select_for_update().filter(user=user, checkout_key=checkout_key).first()
        if existing:
            return existing, False
        locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
        cart_items = list(locked_cart.items.select_for_update().select_related("product", "variant").order_by("pk"))
        if not cart_items:
            raise PricingError("سبد خرید خالی است.")
        product_ids = sorted({item.product_id for item in cart_items})
        variant_ids = sorted({item.variant_id for item in cart_items if item.variant_id})
        products = {row.pk: row for row in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")}
        variants = {row.pk: row for row in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")}
        for item in cart_items:
            if item.product_id not in products:
                raise PricingError("یکی از محصولات سبد دیگر در دسترس نیست.")
            item.product = products[item.product_id]
            if item.variant_id:
                if item.variant_id not in variants:
                    raise PricingError("گونهٔ انتخاب‌شده دیگر در دسترس نیست.")
                item.variant = variants[item.variant_id]
        coupon = None
        if coupon_code:
            coupon = Coupon.objects.select_for_update().filter(code__iexact=coupon_code.strip()).first()
            if coupon is None:
                raise PricingError("کد تخفیف معتبر نیست.")
        quote = build_quote(locked_cart, user, address, coupon_code)
        verify_quote(quote_token, user, locked_cart, address, coupon_code, quote)
        order = Order.objects.create(
            order_number=_new_order_number(), checkout_key=checkout_key, user=user,
            address_snapshot={
                "recipient_name": address.recipient_name,
                "recipient_phone": address.recipient_phone,
                "province": address.province,
                "city": address.city,
                "postal_code": address.postal_code,
                "address": address.address,
                "details": address.details,
            } if address is not None else {},
            shipping_method_label=quote.shipping_label,
            subtotal_toman=quote.subtotal_toman,
            item_discount_toman=quote.item_discount_toman,
            coupon_discount_toman=quote.coupon_discount_toman,
            shipping_toman=quote.shipping_toman,
            tax_rate_percent=quote.tax_rate_percent,
            taxable_base_toman=quote.taxable_base_toman,
            tax_toman=quote.tax_toman,
            total_toman=quote.total_toman,
            coupon=quote.coupon,
            stock_reserved=True,
            reservation_expires_at=timezone.now() + timedelta(seconds=int(getattr(settings, "PAYMENT_RESERVATION_SECONDS", 1800))),
        )
        for line in quote.lines:
            source = next(row for row in cart_items if row.pk == line.cart_item_id)
            product = products[source.product_id]
            variant = variants.get(source.variant_id) if source.variant_id else None
            stock_owner = variant or product
            if not product.is_digital:
                if stock_owner.stock_quantity < line.quantity:
                    raise StockError(f"موجودی «{product.name}» در همین لحظه تغییر کرده است.")
                stock_owner.stock_quantity -= line.quantity
                stock_owner.save(update_fields=("stock_quantity",))
            image = variant.product.image if variant and variant.product.image else product.image
            OrderItem.objects.create(
                order=order, product=product, variant=variant, cart_item_ref=source.pk,
                is_digital=product.is_digital,
                product_name=product.name, sku=variant.sku if variant else product.sku,
                variant_name=variant.title if variant else "",
                image_snapshot=image.name if image else "",
                quantity=line.quantity, regular_unit_toman=line.regular_unit_toman,
                sale_unit_toman=line.sale_unit_toman, item_discount_toman=line.item_discount_toman,
                line_total_toman=line.line_total_toman,
            )
            if not product.is_digital:
                InventoryMovement.objects.create(
                    product=product, variant=variant, delta=-line.quantity,
                    reason=InventoryMovement.Reason.RESERVATION, note="رزرو برای پرداخت سفارش",
                    reference=order.order_number, actor=user,
                )
        if quote.coupon:
            CouponRedemption.objects.create(coupon=quote.coupon, order=order, user=user)
        OrderEvent.objects.create(order=order, status=order.status, message="سفارش ثبت شد و موجودی برای پرداخت رزرو شد.", actor=user)
        AuditLog.objects.create(actor=user, action="order.created", object_type="Order", object_id=order.order_number,
                                changes={"total_toman": order.total_toman})
        return order, True


def cancel_unpaid_order(order, message="سفارش لغو شد.", actor=None):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        from payments.models import PaymentTransaction
        if order.payments.filter(status=PaymentTransaction.Status.PAID).exists() or order.payments.filter(
            status=PaymentTransaction.Status.REVIEW, provider_code="100"
        ).exclude(reference_id="").exists():
            return False
        if order.status == Order.Status.CANCELLED:
            return False
        if order.stock_reserved:
            items = list(order.items.select_for_update().select_related("product", "variant").order_by("pk"))
            product_ids = sorted({item.product_id for item in items if item.product_id})
            variant_ids = sorted({item.variant_id for item in items if item.variant_id})
            products = {row.pk: row for row in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")}
            variants = {row.pk: row for row in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")}
            for item in items:
                product = products.get(item.product_id)
                variant = variants.get(item.variant_id) if item.variant_id else None
                stock_owner = variant or product
                if stock_owner is None or item.is_digital:
                    continue
                stock_owner.stock_quantity = F("stock_quantity") + item.quantity
                stock_owner.save(update_fields=("stock_quantity",))
                stock_owner.refresh_from_db(fields=("stock_quantity",))
                InventoryMovement.objects.create(
                    product=product, variant=variant, delta=item.quantity,
                    reason=InventoryMovement.Reason.RELEASE, note=message[:300],
                    reference=order.order_number, actor=actor,
                )
            order.stock_reserved = False
        order.status = Order.Status.CANCELLED
        order.reservation_expires_at = None
        order.save(update_fields=("status", "stock_reserved", "reservation_expires_at", "updated_at"))
        CouponRedemption.objects.filter(order=order, status=CouponRedemption.Status.PENDING).update(status=CouponRedemption.Status.CANCELLED)
        OrderEvent.objects.create(order=order, status=order.status, message=message[:300], actor=actor)
        AuditLog.objects.create(actor=actor, action="order.cancelled", object_type="Order", object_id=order.order_number)
        return True


def expire_reservations(now=None, limit=200):
    now = now or timezone.now()
    order_ids = list(Order.objects.filter(stock_reserved=True, reservation_expires_at__lte=now).order_by("reservation_expires_at").values_list("pk", flat=True)[:limit])
    expired = 0
    for order_id in order_ids:
        if cancel_unpaid_order(Order.objects.get(pk=order_id), "مهلت پرداخت پایان یافت."):
            expired += 1
            from payments.models import PaymentTransaction
            PaymentTransaction.objects.filter(order_id=order_id, status=PaymentTransaction.Status.AWAITING_VERIFICATION).update(status=PaymentTransaction.Status.EXPIRED, provider_message="مهلت پرداخت پایان یافت.")
    return expired


def clear_ordered_cart(order):
    cart = Cart.objects.filter(user=order.user).first()
    if cart is None:
        return
    with transaction.atomic():
        for ordered in order.items.all():
            if ordered.cart_item_ref is None:
                continue
            item = CartItem.objects.select_for_update().filter(pk=ordered.cart_item_ref, cart=cart).first()
            if item is None:
                continue
            if item.quantity <= ordered.quantity:
                item.delete()
            else:
                item.quantity -= ordered.quantity
                item.save(update_fields=("quantity", "updated_at"))


def adjust_inventory(*, product, variant=None, delta, note, actor):
    if not delta:
        raise StockError("تغییر موجودی نمی‌تواند صفر باشد.")
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product.pk)
        if variant:
            variant = ProductVariant.objects.select_for_update().get(pk=variant.pk, product=product)
        owner = variant or product
        if owner.stock_quantity + delta < 0:
            raise StockError("موجودی نمی‌تواند منفی شود.")
        owner.stock_quantity += delta
        owner.save(update_fields=("stock_quantity",))
        movement = InventoryMovement.objects.create(
            product=product, variant=variant, delta=delta, reason=InventoryMovement.Reason.ADJUSTMENT,
            note=note[:300], actor=actor,
        )
        AuditLog.objects.create(actor=actor, action="inventory.adjusted", object_type="InventoryMovement",
                                object_id=str(movement.pk), changes={"product": product.sku, "delta": delta, "note": note[:300]})
        return movement


def change_order_status(order, new_status, actor, tracking_number=""):
    allowed = {
        Order.Status.PROCESSING: {Order.Status.PACKED},
        Order.Status.PACKED: {Order.Status.SHIPPED},
        Order.Status.SHIPPED: {Order.Status.DELIVERED},
        Order.Status.CANCEL_REQUESTED: {Order.Status.PROCESSING},
    }
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if new_status == Order.Status.CANCELLED:
            if order.status == Order.Status.AWAITING_PAYMENT:
                if not cancel_unpaid_order(order, "سفارش توسط مدیر لغو شد.", actor):
                    raise PricingError("تراکنش تأییدشده یا نیازمند بررسی را نمی‌توان به‌عنوان سفارش پرداخت‌نشده لغو کرد.")
                return True
            from payments.models import PaymentTransaction
            if order.payments.filter(status=PaymentTransaction.Status.PAID).exists() or order.payments.filter(
                status=PaymentTransaction.Status.REVIEW, provider_code="100"
            ).exclude(reference_id="").exists():
                raise PricingError("سفارش پرداخت‌شده باید از مسیر درخواست بازپرداخت رسیدگی شود.")
            if not cancel_unpaid_order(order, "سفارش توسط مدیر لغو شد.", actor):
                raise PricingError("لغو سفارش انجام نشد؛ وضعیت پرداخت را بررسی کنید.")
            return True
        if new_status not in allowed.get(order.status, set()):
            raise PricingError("این تغییر وضعیت مجاز نیست.")
        if new_status == Order.Status.SHIPPED and not tracking_number.strip():
            raise PricingError("برای ثبت ارسال، شمارهٔ پیگیری لازم است.")
        old_status = order.status
        order.status = new_status
        if tracking_number:
            order.shipping_tracking_number = tracking_number.strip()[:120]
        order.save(update_fields=("status", "shipping_tracking_number", "updated_at"))
        OrderEvent.objects.create(order=order, status=new_status, message=f"وضعیت سفارش: {order.get_status_display()}.", actor=actor)
        AuditLog.objects.create(actor=actor, action="order.status_changed", object_type="Order", object_id=order.order_number,
                                changes={"from": old_status, "to": new_status, "tracking": order.shipping_tracking_number})
        return True
