import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from catalog.downloads import stream_asset
from catalog.models import DigitalAsset, Product, ProductVariant

from .forms import CancellationForm, CheckoutForm
from .models import CancellationRequest, CartItem, Order, OrderEvent, OrderItem, WishlistItem
from .pricing import PricingError, QuoteChanged, build_quote, sign_quote
from .services import (
    StockError, add_to_cart, create_checkout_order, get_cart, merge_guest_cart,
    update_cart_item,
)


def _anonymous_cart_user(request):
    return request.user if request.user.is_authenticated else None


def cart_detail(request):
    cart = get_cart(request)
    quote = None
    error = ""
    if cart.items.exists():
        try:
            quote = build_quote(cart, _anonymous_cart_user(request))
        except PricingError as exc:
            error = str(exc)
    return render(request, "commerce/cart.html", {"cart": cart, "quote": quote, "pricing_error": error})


@require_POST
def cart_add(request, slug):
    product = get_object_or_404(Product, slug=slug, status=Product.Status.PUBLISHED)
    variant = None
    variant_id = request.POST.get("variant")
    if variant_id:
        variant = get_object_or_404(ProductVariant, pk=variant_id, product=product, is_active=True)
    try:
        quantity = int(request.POST.get("quantity", "1"))
        add_to_cart(get_cart(request), product, variant, quantity)
    except (ValueError, StockError) as exc:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": str(exc) or "تعداد واردشده معتبر نیست."}, status=400)
        messages.error(request, str(exc) or "تعداد واردشده معتبر نیست.")
        return redirect("catalog:product", slug=slug)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        count = sum(get_cart(request).items.values_list("quantity", flat=True))
        return JsonResponse({"ok": True, "cart_count": count})
    messages.success(request, "محصول به سبد خرید اضافه شد.")
    return redirect("commerce:cart")


@require_POST
def cart_update(request, item_id):
    cart = get_cart(request)
    try:
        quantity = int(request.POST.get("quantity", "0"))
        update_cart_item(cart, item_id, quantity)
    except (ValueError, CartItem.DoesNotExist, StockError):
        messages.error(request, "تغییر تعداد انجام نشد؛ موجودی را بررسی کنید.")
    else:
        messages.success(request, "سبد خرید به‌روز شد.")
    return redirect("commerce:cart")


@require_POST
def cart_decrease(request, item_id):
    cart = get_cart(request)
    item = CartItem.objects.filter(pk=item_id, cart=cart).first()
    if item is None:
        return JsonResponse({"ok": False, "error": "این مورد در سبد نیست."}, status=404)
    if item.quantity <= 1:
        item.delete()
    else:
        item.quantity -= 1
        item.save(update_fields=["quantity"])
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not is_ajax:
        return redirect("commerce:cart")
    from django.template.loader import render_to_string
    items = list(cart.items.select_related("product", "variant").order_by("-pk")[:5])
    count = sum(cart.items.values_list("quantity", flat=True))
    html = render_to_string("_cart_dropdown_body.html", {"cart_mini_items": items, "cart_count": count}, request=request)
    return JsonResponse({"ok": True, "cart_count": count, "html": html})


@require_POST
def cart_remove(request, item_id):
    CartItem.objects.filter(pk=item_id, cart=get_cart(request)).delete()
    messages.success(request, "محصول از سبد حذف شد.")
    return redirect("commerce:cart")


@login_required
def wishlist(request):
    items = request.user.wishlist_items.select_related("product", "variant", "product__category").all()
    return render(request, "commerce/wishlist.html", {"items": items})


@require_POST
def wishlist_add(request, slug):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('account:login')}?next={request.path}")
    product = get_object_or_404(Product, slug=slug, status=Product.Status.PUBLISHED)
    variant_id = request.POST.get("variant")
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product, is_active=True) if variant_id else None
    WishlistItem.objects.get_or_create(user=request.user, product=product, variant=variant)
    messages.success(request, "محصول به فهرست علاقه‌مندی‌ها اضافه شد.")
    return redirect("commerce:wishlist")


@login_required
@require_POST
def wishlist_remove(request, item_id):
    WishlistItem.objects.filter(pk=item_id, user=request.user).delete()
    messages.success(request, "محصول از علاقه‌مندی‌ها حذف شد.")
    return redirect("commerce:wishlist")


@login_required
@require_POST
def wishlist_to_cart(request, item_id):
    item = get_object_or_404(WishlistItem.objects.select_related("product", "variant"), pk=item_id, user=request.user)
    try:
        add_to_cart(get_cart(request), item.product, item.variant, 1)
    except StockError as exc:
        messages.error(request, str(exc))
        return redirect("commerce:wishlist")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        count = sum(get_cart(request).items.values_list("quantity", flat=True))
        return JsonResponse({"ok": True, "cart_count": count})
    messages.success(request, "محصول به سبد خرید اضافه شد.")
    return redirect("commerce:cart")


@login_required
def checkout(request):
    cart = get_cart(request)
    if not cart.items.exists():
        messages.info(request, "سبد خرید خالی است.")
        return redirect("commerce:cart")
    needs_address = cart.items.filter(product__product_type=Product.ProductType.PHYSICAL).exists()
    if needs_address and not request.user.addresses.exists():
        messages.info(request, "برای ادامه، ابتدا یک نشانی ثبت کنید.")
        return redirect(f"{reverse('account:addresses')}?next={reverse('commerce:checkout')}")
    form = CheckoutForm(request.POST or None, user=request.user, needs_address=needs_address)
    quote = None
    token = ""
    if request.method == "POST" and form.is_valid():
        address = form.cleaned_data["address"] if needs_address else None
        code = form.cleaned_data["coupon_code"]
        try:
            order, created = create_checkout_order(
                cart=cart, user=request.user, address=address, coupon_code=code,
                checkout_key=form.cleaned_data["checkout_key"], quote_token=form.cleaned_data["quote_token"],
            )
        except QuoteChanged as exc:
            messages.warning(request, str(exc))
        except PricingError as exc:
            form.add_error(None, str(exc))
        else:
            from payments.models import PaymentTransaction
            from payments.services import initiate_payment
            payment = PaymentTransaction.objects.filter(order=order).order_by("created_at").first()
            if payment is None:
                from payments.services import create_transaction
                payment = create_transaction(order)
            if payment.status == PaymentTransaction.Status.PAID:
                return redirect("commerce:order_detail", order_number=order.order_number)
            if payment.authority and payment.status == PaymentTransaction.Status.AWAITING_VERIFICATION:
                from django.conf import settings
                return redirect(settings.ZARINPAL_PAYMENT_BASE_URL + payment.authority)
            try:
                payment_url = initiate_payment(payment, request)
            except Exception:
                messages.error(request, "درگاه پرداخت در دسترس نیست. مبلغی کسر نشده است؛ سبد شما حفظ شد.")
                return redirect("commerce:cart")
            return redirect(payment_url)
    if form.is_bound and not form.errors:
        form.add_error(None, "لطفاً خلاصهٔ سفارش را دوباره بررسی و تأیید کنید.")
    address = form.cleaned_data.get("address") if form.is_bound and form.is_valid() else None
    if address is None and needs_address:
        address = request.user.addresses.filter(is_default=True).first() or request.user.addresses.first()
    code = form.cleaned_data.get("coupon_code", "") if form.is_bound and form.is_valid() else (request.POST.get("coupon_code", "") if request.method == "POST" else "")
    try:
        quote = build_quote(cart, request.user, address, code)
        token = sign_quote(request.user, cart, address, code, quote)
    except PricingError as exc:
        form.add_error(None, str(exc))
    if not form.is_bound:
        form.initial["quote_token"] = token
        form.initial["checkout_key"] = uuid.uuid4()
    elif token:
        form.data = form.data.copy()
        form.data["quote_token"] = token
    return render(request, "commerce/checkout.html", {"cart": cart, "form": form, "quote": quote, "addresses": request.user.addresses.all(), "needs_address": needs_address})


@login_required
def order_history(request):
    orders = request.user.orders.prefetch_related("items", "payments").all()
    return render(request, "commerce/orders.html", {"orders": orders})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "events", "payments", "payments__refunds"),
        order_number=order_number,
        user=request.user,
    )
    return render(request, "commerce/order_detail.html", {"order": order})


@login_required
@require_POST
def request_cancellation(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if order.status not in (Order.Status.PROCESSING, Order.Status.PACKED):
        messages.error(request, "برای این سفارش درخواست لغو ثبت نمی‌شود.")
        return redirect("commerce:order_detail", order_number=order_number)
    form = CancellationForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk, user=request.user)
            if order.status not in (Order.Status.PROCESSING, Order.Status.PACKED):
                messages.error(request, "وضعیت سفارش تغییر کرده است و دیگر درخواست لغو نمی‌پذیرد.")
                return redirect("commerce:order_detail", order_number=order_number)
            req, created = CancellationRequest.objects.get_or_create(order=order, defaults={
                "user": request.user, "reason": form.cleaned_data["reason"],
                "previous_order_status": order.status,
            })
            if created:
                order.status = Order.Status.CANCEL_REQUESTED
                order.save(update_fields=("status", "updated_at"))
                OrderEvent.objects.create(order=order, status=order.status, message="درخواست لغو برای بررسی ثبت شد.", actor=request.user)
                messages.success(request, "درخواست لغو برای بررسی ثبت شد.")
            else:
                messages.info(request, "برای این سفارش قبلاً درخواست لغو ثبت شده است.")
    return redirect("commerce:order_detail", order_number=order_number)


@login_required
def my_downloads(request):
    items = (OrderItem.objects.filter(order__user=request.user, is_digital=True, order__status__in=[
        Order.Status.PROCESSING, Order.Status.PACKED, Order.Status.SHIPPED, Order.Status.DELIVERED])
        .select_related("order", "product").prefetch_related("product__assets").order_by("-order__placed_at"))
    return render(request, "commerce/my_downloads.html", {"items": items, "limit": settings.DIGITAL_DOWNLOAD_LIMIT})


@login_required
def paid_download(request, item_id, asset_id):
    item = get_object_or_404(OrderItem.objects.select_related("order"), pk=item_id, order__user=request.user, is_digital=True)
    if not item.order.downloads_open:
        messages.error(request, "دانلود این سفارش فعال نیست.")
        return redirect("commerce:order_detail", order_number=item.order.order_number)
    asset = get_object_or_404(DigitalAsset, pk=asset_id, product_id=item.product_id, is_active=True)
    limit = int(settings.DIGITAL_DOWNLOAD_LIMIT)
    with transaction.atomic():
        updated = OrderItem.objects.filter(pk=item.pk, download_count__lt=limit).update(download_count=F("download_count") + 1)
    if not updated:
        messages.error(request, "سقف دفعات دانلود این خرید تمام شده است. با پشتیبانی تماس بگیرید.")
        return redirect("commerce:order_detail", order_number=item.order.order_number)
    return stream_asset(asset, "download.paid", {"order": item.order.order_number, "user": request.user.pk})
