import csv
import secrets
from datetime import timedelta
from functools import wraps
from urllib.parse import quote

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from catalog.forms import CategoryForm, DigitalAssetFormSet, DigitalProductForm, ProductForm, ProductImageFormSet, ProductVariantFormSet
from catalog.models import Category, InventoryMovement, Product, ProductImage, ProductVariant
from commerce.forms import OrderStatusForm
from commerce.models import CancellationRequest, Coupon, Order, OrderEvent
from commerce.pricing import PricingError
from commerce.services import adjust_inventory, cancel_unpaid_order, change_order_status
from payments.models import PaymentTransaction, RefundRecord
from .forms import (
    BannerForm, ContentPageForm, CouponForm, FAQForm, HomeSectionForm, RefundReconcileForm,
    RefundRequestForm, ShippingRateForm, StoreSettingsForm,
)
from .models import AuditLog, ContentPage, FAQ, HeroBanner, HomeSection, ShippingRate, StoreSettings


def manager_required(permission):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.urls import reverse
                return redirect(f"{reverse('account:login')}?next={quote(request.get_full_path())}")
            if not request.user.is_staff or not request.user.has_perm(permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def _audit(request, action, object_type, object_id="", changes=None):
    AuditLog.objects.create(
        actor=request.user, action=action, object_type=object_type, object_id=str(object_id),
        changes=changes or {}, source_ip=request.META.get("REMOTE_ADDR") or None,
    )


def _snapshot(instance, fields):
    return {field: str(getattr(instance, field)) for field in fields}


@manager_required("storefront.view_store_dashboard")
def dashboard(request):
    try:
        days = min(365, max(1, int(request.GET.get("days", 30))))
    except (TypeError, ValueError):
        days = 30
    since = timezone.now() - timedelta(days=days)
    paid = PaymentTransaction.objects.filter(status=PaymentTransaction.Status.PAID, verified_at__gte=since)
    gross = paid.aggregate(value=Sum("amount_toman"))["value"] or 0
    refunded = RefundRecord.objects.filter(status=RefundRecord.Status.CONFIRMED, reconciled_at__gte=since).aggregate(value=Sum("amount_toman"))["value"] or 0
    revenue = max(0, gross - refunded)
    paid_order_ids = PaymentTransaction.objects.filter(status=PaymentTransaction.Status.PAID, verified_at__gte=since).values_list("order_id", flat=True)
    paid_count = Order.objects.filter(pk__in=paid_order_ids).distinct().count()
    bestsellers = Product.objects.filter(status=Product.Status.PUBLISHED).annotate(
        sold=Sum("order_items__quantity", filter=Q(order_items__order__payments__status=PaymentTransaction.Status.PAID))
    ).order_by("-sold", "name")[:5]
    low_stock = Product.objects.filter(status=Product.Status.PUBLISHED).annotate(
        variant_count=Count("variants", filter=Q(variants__is_active=True), distinct=True)
    ).filter(
        Q(variant_count=0, stock_quantity__lte=F("low_stock_threshold")) |
        Q(variant_count__gt=0, variants__is_active=True, variants__stock_quantity__lte=F("variants__low_stock_threshold"))
    ).distinct()[:10]
    return render(request, "management/dashboard.html", {
        "days": days,
        "total_orders": Order.objects.filter(placed_at__gte=since).count(),
        "paid_orders": paid_count,
        "pending_payments": Order.objects.filter(status__in=(Order.Status.AWAITING_PAYMENT, Order.Status.PAYMENT_REVIEW)).count(),
        "cancelled_orders": Order.objects.filter(status=Order.Status.CANCELLED, placed_at__gte=since).count(),
        "revenue": revenue,
        "average_order_value": revenue // paid_count if paid_count else 0,
        "bestsellers": bestsellers,
        "low_stock": low_stock,
        "awaiting": Order.objects.filter(status__in=(Order.Status.PROCESSING, Order.Status.PACKED)).order_by("placed_at")[:10],
        "recent_orders": Order.objects.select_related("user").prefetch_related("payments").order_by("-placed_at")[:10],
    })


@manager_required("catalog.manage_products")
def product_list(request):
    products = Product.objects.exclude(product_type=Product.ProductType.DIGITAL).select_related("category").prefetch_related("variants")
    query = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    if status in Product.Status.values:
        products = products.filter(status=status)
    page = Paginator(products, 25).get_page(request.GET.get("page"))
    return render(request, "management/products.html", {
        "page_obj": page, "products": page.object_list, "query": query, "status": status,
        "product_statuses": Product.Status.choices,
    })


@manager_required("catalog.manage_products")
def product_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    if product is not None and product.is_digital:
        return redirect("storefront:manager_digital_edit", pk=product.pk)
    old = _snapshot(product, ("name", "sku", "price_toman", "sale_price_toman", "status")) if product else {}
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    form.fields["slug"].required = False
    variants = ProductVariantFormSet(request.POST or None, request.FILES or None, instance=product, prefix="variants")
    images = ProductImageFormSet(request.POST or None, request.FILES or None, instance=product, prefix="images")
    if request.method == "POST" and form.is_valid() and variants.is_valid() and images.is_valid():
        with transaction.atomic():
            product = form.save()
            variants.instance = product
            images.instance = product
            variants.save()
            images.save()
            new = _snapshot(product, ("name", "sku", "price_toman", "sale_price_toman", "status"))
            _audit(request, "product.created" if not old else "product.updated", "Product", product.pk, {"before": old, "after": new})
        messages.success(request, "محصول ذخیره شد.")
        return redirect("storefront:manager_product_edit", pk=product.pk)
    return render(request, "management/product_form.html", {"form": form, "variants": variants, "images": images, "product": product})


@manager_required("catalog.manage_products")
@require_POST
def product_duplicate(request, pk):
    source = get_object_or_404(Product.objects.prefetch_related("variants", "gallery"), pk=pk)
    token = secrets.token_hex(3).upper()
    duplicate = Product.objects.create(
        name=f"{source.name} — نسخهٔ کپی", slug=f"{source.slug[:180]}-copy-{token.lower()}",
        sku=f"{source.sku[:56]}-C{token}", short_description=source.short_description,
        description=source.description, category=source.category, brand=source.brand,
        specifications=source.specifications, image=source.image.name if source.image else "",
        price_toman=source.price_toman, sale_price_toman=source.sale_price_toman,
        stock_quantity=0, low_stock_threshold=source.low_stock_threshold, status=Product.Status.DRAFT,
        is_featured=False, is_new=False, is_bestseller=False,
    )
    for variant in source.variants.all():
        ProductVariant.objects.create(
            product=duplicate, title=variant.title, sku=f"{variant.sku[:56]}-C{token}",
            price_override_toman=variant.price_override_toman, sale_override_toman=variant.sale_override_toman,
            stock_quantity=0, low_stock_threshold=variant.low_stock_threshold, is_active=variant.is_active,
        )
    for image in source.gallery.all():
        ProductImage.objects.create(product=duplicate, image=image.image.name, alt_text=image.alt_text, position=image.position)
    _audit(request, "product.duplicated", "Product", duplicate.pk, {"source": source.pk})
    messages.success(request, "یک پیش‌نویس کپی‌شده ساخته شد؛ موجودی آن صفر است.")
    return redirect("storefront:manager_product_edit", pk=duplicate.pk)


@manager_required("catalog.manage_categories")
def category_list(request):
    categories = Category.objects.select_related("parent").annotate(product_count=Count("products")).all()
    return render(request, "management/categories.html", {"categories": categories})


@manager_required("catalog.manage_categories")
def category_edit(request, pk=None):
    category = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category)
    form.fields["slug"].required = False
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        _audit(request, "category.saved", "Category", obj.pk, {"name": obj.name, "active": obj.is_active})
        messages.success(request, "دسته ذخیره شد.")
        return redirect("storefront:manager_categories")
    return render(request, "management/category_form.html", {"form": form, "category": category})


@manager_required("catalog.manage_categories")
@require_POST
def category_deactivate(request, pk):
    category = get_object_or_404(Category, pk=pk)
    category.is_active = False
    category.save(update_fields=("is_active", "updated_at"))
    _audit(request, "category.deactivated", "Category", category.pk)
    messages.success(request, "دسته از فروشگاه پنهان شد؛ محصولات آن حذف نشدند.")
    return redirect("storefront:manager_categories")


class InventoryAdjustmentForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.all(), label="محصول")
    variant = forms.ModelChoiceField(queryset=ProductVariant.objects.none(), label="گونه (اختیاری)", required=False)
    delta = forms.IntegerField(label="تغییر موجودی؛ افزایش مثبت، کاهش منفی")
    note = forms.CharField(label="دلیل تغییر", max_length=300)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        product_id = self.data.get("product") or self.initial.get("product")
        if product_id:
            self.fields["variant"].queryset = ProductVariant.objects.filter(product_id=product_id)


@manager_required("catalog.manage_inventory")
def inventory(request):
    form = InventoryAdjustmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            adjust_inventory(product=form.cleaned_data["product"], variant=form.cleaned_data["variant"],
                             delta=form.cleaned_data["delta"], note=form.cleaned_data["note"], actor=request.user)
        except PricingError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "تغییر موجودی ثبت شد.")
            return redirect("storefront:manager_inventory")
    movements = InventoryMovement.objects.select_related("product", "variant", "actor")[:50]
    return render(request, "management/inventory.html", {"form": form, "movements": movements})


def _filtered_orders(request):
    orders = Order.objects.select_related("user").prefetch_related("payments")
    query = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    payment_status = request.GET.get("payment", "")
    if query:
        orders = orders.filter(Q(order_number__icontains=query) | Q(user__phone_number__icontains=query))
    if status in Order.Status.values:
        orders = orders.filter(status=status)
    if payment_status in PaymentTransaction.Status.values:
        orders = orders.filter(payments__status=payment_status)
    date_from = parse_date(request.GET.get("from", ""))
    date_to = parse_date(request.GET.get("to", ""))
    if date_from:
        orders = orders.filter(placed_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(placed_at__date__lte=date_to)
    filters = {"q": query, "status": status, "payment": payment_status,
               "from": request.GET.get("from", ""), "to": request.GET.get("to", "")}
    return orders.distinct().order_by("-placed_at"), filters


@manager_required("commerce.manage_orders")
def order_list(request):
    orders, filters = _filtered_orders(request)
    page = Paginator(orders, 30).get_page(request.GET.get("page"))
    return render(request, "management/orders.html", {
        "page_obj": page, "orders": page.object_list, "filters": filters,
        "statuses": Order.Status.choices, "payment_statuses": PaymentTransaction.Status.choices,
    })


@manager_required("commerce.view_financial_reports")
def order_export(request):
    orders, _ = _filtered_orders(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="orders.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(("شماره سفارش", "تاریخ", "مشتری", "وضعیت سفارش", "وضعیت پرداخت", "مبلغ تومان", "هزینه ارسال", "مالیات"))
    for order in orders.iterator(chunk_size=500):
        payment = order.payments.order_by("-created_at").first()
        writer.writerow((order.order_number, timezone.localtime(order.placed_at).isoformat(), order.user.phone_number,
                         order.get_status_display(), payment.get_status_display() if payment else "—",
                         order.total_toman, order.shipping_toman, order.tax_toman))
    return response


@manager_required("commerce.manage_orders")
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.select_related("user", "coupon").prefetch_related("items", "events", "payments", "payments__refunds"),
        order_number=order_number,
    )
    return render(request, "management/order_detail.html", {
        "order": order, "status_form": OrderStatusForm(initial={"status": order.status}),
        "refund_form": RefundRequestForm(), "cancellation": getattr(order, "cancellation_request", None),
    })


@manager_required("commerce.manage_orders")
@require_POST
def order_status(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    form = OrderStatusForm(request.POST)
    if form.is_valid():
        try:
            change_order_status(order, form.cleaned_data["status"], request.user, form.cleaned_data["tracking_number"])
        except PricingError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "وضعیت سفارش ثبت شد.")
    return redirect("storefront:manager_order_detail", order_number=order_number)


@manager_required("commerce.manage_orders")
@require_POST
def cancellation_resolution(request, order_number):
    action = request.POST.get("action")
    if action not in ("reject", "approve"):
        messages.error(request, "عملیات معتبر نیست.")
        return redirect("storefront:manager_order_detail", order_number=order_number)

    with transaction.atomic():
        cancellation = get_object_or_404(
            CancellationRequest.objects.select_for_update(), order__order_number=order_number,
        )
        order = Order.objects.select_for_update().get(pk=cancellation.order_id)
        if cancellation.status != CancellationRequest.Status.REQUESTED:
            messages.error(request, "این درخواست قبلاً تعیین تکلیف شده است.")
            return redirect("storefront:manager_order_detail", order_number=order_number)

        if action == "reject":
            cancellation.status = CancellationRequest.Status.REJECTED
            cancellation.manager_note = request.POST.get("note", "")[:300]
            cancellation.resolved_at = timezone.now()
            cancellation.save(update_fields=("status", "manager_note", "resolved_at"))
            order.status = cancellation.previous_order_status if cancellation.previous_order_status in (
                Order.Status.PROCESSING, Order.Status.PACKED,
            ) else Order.Status.PROCESSING
            order.save(update_fields=("status", "updated_at"))
            OrderEvent.objects.create(order=order, status=order.status, message="درخواست لغو رد شد.", actor=request.user)
            _audit(request, "order.cancellation_rejected", "Order", order_number)
            messages.info(request, "درخواست لغو رد شد.")
        else:
            payment = PaymentTransaction.objects.select_for_update().filter(
                order=order,
                status__in=(PaymentTransaction.Status.PAID, PaymentTransaction.Status.PARTIALLY_REFUNDED, PaymentTransaction.Status.REVIEW),
            ).order_by("-created_at").first()
            if payment and payment.status == PaymentTransaction.Status.REVIEW and not (
                payment.provider_code == "100" and payment.reference_id
            ):
                messages.error(request, "وضعیت پرداخت هنوز قطعی نیست؛ سفارش پس از بررسی پرداخت قابل لغو است.")
                return redirect("storefront:manager_order_detail", order_number=order_number)

            if payment:
                if not request.user.has_perm("payments.manage_refunds"):
                    raise PermissionDenied
                reserved = payment.refunds.exclude(status=RefundRecord.Status.FAILED).aggregate(
                    value=Sum("amount_toman"),
                )["value"] or 0
                remaining = max(0, payment.amount_toman - reserved)
                if remaining:
                    RefundRecord.objects.create(
                        payment=payment, amount_toman=remaining,
                        reason="لغو سفارش به درخواست مشتری", requested_by=request.user,
                    )
                cancellation.status = CancellationRequest.Status.APPROVED
                cancellation.resolved_at = timezone.now()
                cancellation.save(update_fields=("status", "resolved_at"))
                _audit(request, "order.cancellation_refund_requested", "Order", order_number, {"amount_toman": remaining})
                if remaining:
                    messages.info(request, "درخواست بازپرداخت ثبت شد؛ سفارش پس از تسویهٔ بیرونی نهایی می‌شود.")
                else:
                    messages.info(request, "مبلغ پرداخت قبلاً در درخواست‌های بازپرداخت پوشش داده شده است؛ سفارش پس از تطبیق نهایی می‌شود.")
            else:
                if not cancel_unpaid_order(order, "لغو سفارش به درخواست مشتری تأیید شد.", request.user):
                    messages.error(request, "لغو سفارش انجام نشد؛ وضعیت سفارش و پرداخت را بررسی کنید.")
                    return redirect("storefront:manager_order_detail", order_number=order_number)
                cancellation.status = CancellationRequest.Status.APPROVED
                cancellation.resolved_at = timezone.now()
                cancellation.save(update_fields=("status", "resolved_at"))
                messages.success(request, "سفارش لغو شد و موجودی آزاد شد.")
    return redirect("storefront:manager_order_detail", order_number=order_number)


@manager_required("payments.manage_refunds")
@require_POST
def refund_request(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    payment = order.payments.filter(status__in=(
        PaymentTransaction.Status.PAID,
        PaymentTransaction.Status.PARTIALLY_REFUNDED,
        PaymentTransaction.Status.REVIEW,
    )).order_by("-created_at").first()
    if payment is None:
        messages.error(request, "برای این سفارش پرداخت تأییدشده‌ای وجود ندارد.")
        return redirect("storefront:manager_order_detail", order_number=order_number)
    if payment.status == PaymentTransaction.Status.REVIEW and not (payment.provider_code == "100" and payment.reference_id):
        messages.error(request, "پرداخت در وضعیت بررسی است اما رسید تأییدشده‌ای برای بازپرداخت ثبت نشده است.")
        return redirect("storefront:manager_order_detail", order_number=order_number)
    form = RefundRequestForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            payment = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
            can_refund = payment.status in (PaymentTransaction.Status.PAID, PaymentTransaction.Status.PARTIALLY_REFUNDED) or (
                payment.status == PaymentTransaction.Status.REVIEW
                and payment.provider_code == "100" and bool(payment.reference_id)
            )
            if not can_refund:
                messages.error(request, "وضعیت پرداخت تغییر کرده است؛ امکان ثبت بازپرداخت وجود ندارد.")
            else:
                reserved = payment.refunds.exclude(status=RefundRecord.Status.FAILED).aggregate(
                    value=Sum("amount_toman"),
                )["value"] or 0
                if form.cleaned_data["amount_toman"] + reserved > payment.amount_toman:
                    messages.error(request, "مجموع بازپرداخت‌ها از مبلغ پرداخت‌شده بیشتر می‌شود.")
                else:
                    refund = form.save(commit=False)
                    refund.payment, refund.requested_by = payment, request.user
                    refund.save()
                    _audit(request, "refund.requested", "RefundRecord", refund.pk, {"amount_toman": refund.amount_toman, "order": order_number})
                    messages.info(request, "درخواست ثبت شد و تا ثبت رسید بیرونی، بازپرداخت انجام‌شده محسوب نمی‌شود.")
    else:
        messages.error(request, "فرم بازپرداخت معتبر نیست.")
    return redirect("storefront:manager_order_detail", order_number=order_number)


@manager_required("payments.manage_refunds")
@require_POST
def refund_reconcile(request, pk):
    refund = get_object_or_404(RefundRecord.objects.select_related("payment", "payment__order"), pk=pk)
    form = RefundReconcileForm(request.POST)
    if not form.is_valid():
        messages.error(request, "برای ثبت وضعیت، فرم و شناسهٔ رسید را کامل کنید.")
        return redirect("storefront:manager_order_detail", order_number=refund.payment.order.order_number)
    new_status = form.cleaned_data["status"]
    with transaction.atomic():
        refund = RefundRecord.objects.select_for_update().get(pk=refund.pk)
        payment = PaymentTransaction.objects.select_for_update().select_related("order").get(pk=refund.payment_id)
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        allowed_transitions = {
            RefundRecord.Status.REQUESTED: {
                RefundRecord.Status.SUBMITTED, RefundRecord.Status.CONFIRMED, RefundRecord.Status.FAILED,
            },
            RefundRecord.Status.SUBMITTED: {RefundRecord.Status.CONFIRMED, RefundRecord.Status.FAILED},
        }
        if new_status not in allowed_transitions.get(refund.status, set()):
            messages.error(request, "این وضعیت بازپرداخت دیگر قابل تغییر نیست.")
            return redirect("storefront:manager_order_detail", order_number=order.order_number)
        if new_status == RefundRecord.Status.CONFIRMED:
            already = payment.refunds.exclude(pk=refund.pk).filter(status=RefundRecord.Status.CONFIRMED).aggregate(value=Sum("amount_toman"))["value"] or 0
            if already + refund.amount_toman > payment.amount_toman:
                messages.error(request, "مجموع بازپرداخت تأییدشده از مبلغ پرداخت بیشتر می‌شود.")
                return redirect("storefront:manager_order_detail", order_number=order.order_number)
        refund.status = new_status
        refund.external_reference = form.cleaned_data["external_reference"].strip()
        refund.reconciled_by = request.user
        refund.reconciled_at = timezone.now()
        refund.save(update_fields=("status", "external_reference", "reconciled_by", "reconciled_at"))
        confirmed = payment.refunds.filter(status=RefundRecord.Status.CONFIRMED).aggregate(value=Sum("amount_toman"))["value"] or 0
        if confirmed >= payment.amount_toman:
            payment.status = PaymentTransaction.Status.REFUNDED
            payment.save(update_fields=("status", "updated_at"))
            order.status = Order.Status.REFUNDED
            order.save(update_fields=("status", "updated_at"))
            OrderEvent.objects.create(order=order, status=Order.Status.REFUNDED, message="بازپرداخت در سوابق بیرونی ثبت و تطبیق شد.", actor=request.user)
        elif confirmed:
            payment.status = PaymentTransaction.Status.PARTIALLY_REFUNDED
            payment.save(update_fields=("status", "updated_at"))
        _audit(request, "refund.reconciled", "RefundRecord", refund.pk, {"status": new_status, "reference": refund.external_reference})
    messages.success(request, "ثبت مالی بازپرداخت به‌روزرسانی شد.")
    return redirect("storefront:manager_order_detail", order_number=order.order_number)


@manager_required("storefront.manage_store_settings")
def store_settings(request):
    instance = StoreSettings.get_solo()
    before = {key: str(getattr(instance, key)) for key in
              ("store_name", "default_shipping_toman", "free_shipping_threshold_toman", "tax_enabled", "tax_rate_percent", "shipping_is_taxable")}
    form = StoreSettingsForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        after = {key: str(getattr(obj, key)) for key in before}
        _audit(request, "store.settings_updated", "StoreSettings", obj.pk, {"before": before, "after": after})
        messages.success(request, "تنظیمات فروشگاه ذخیره شد.")
        return redirect("storefront:manager_settings")
    return render(request, "management/settings.html", {
        "form": form,
        "sms_configured": bool(settings.KAVENEGAR_API_KEY and settings.KAVENEGAR_OTP_TEMPLATE),
        "payment_configured": bool(settings.ZARINPAL_MERCHANT_ID),
        "sandbox": settings.ZARINPAL_SANDBOX,
    })


@manager_required("storefront.manage_store_settings")
def shipping_rates(request):
    return render(request, "management/shipping.html", {
        "rates": ShippingRate.objects.all(), "default_charge": StoreSettings.get_solo().default_shipping_toman,
    })


@manager_required("storefront.manage_store_settings")
def shipping_rate_edit(request, pk=None):
    rate = get_object_or_404(ShippingRate, pk=pk) if pk else None
    form = ShippingRateForm(request.POST or None, instance=rate)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        _audit(request, "shipping.rate_saved", "ShippingRate", obj.pk, {"name": obj.name, "charge_toman": obj.charge_toman, "province": obj.province, "city": obj.city})
        messages.success(request, "روش ارسال ذخیره شد.")
        return redirect("storefront:manager_shipping")
    return render(request, "management/simple_form.html", {"form": form, "title": "روش ارسال", "back_url": "storefront:manager_shipping"})


@manager_required("storefront.manage_store_content")
def banners(request):
    return render(request, "management/content_list.html", {
        "title": "بنرهای صفحهٔ اصلی", "items": HeroBanner.objects.all(),
        "create_url": "storefront:manager_banner_create", "edit_name": "storefront:manager_banner_edit", "kind": "banner",
    })


@manager_required("storefront.manage_store_content")
def banner_edit(request, pk=None):
    obj = get_object_or_404(HeroBanner, pk=pk) if pk else None
    form = BannerForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        _audit(request, "content.banner_saved", "HeroBanner", saved.pk, {"title": saved.title, "active": saved.is_active})
        messages.success(request, "بنر ذخیره شد.")
        return redirect("storefront:manager_banners")
    return render(request, "management/simple_form.html", {"form": form, "title": "بنر صفحهٔ اصلی", "back_url": "storefront:manager_banners"})


@manager_required("storefront.manage_store_content")
def home_sections(request):
    return render(request, "management/content_list.html", {
        "title": "بخش‌های صفحهٔ اصلی", "items": HomeSection.objects.all(),
        "create_url": "storefront:manager_section_create", "edit_name": "storefront:manager_section_edit", "kind": "section",
    })


@manager_required("storefront.manage_store_content")
def home_section_edit(request, pk=None):
    obj = get_object_or_404(HomeSection, pk=pk) if pk else None
    form = HomeSectionForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        _audit(request, "content.section_saved", "HomeSection", saved.pk, {"title": saved.title, "visible": saved.is_visible})
        messages.success(request, "بخش صفحهٔ اصلی ذخیره شد.")
        return redirect("storefront:manager_sections")
    return render(request, "management/simple_form.html", {"form": form, "title": "بخش صفحهٔ اصلی", "back_url": "storefront:manager_sections"})


@manager_required("storefront.manage_store_content")
def content_pages(request):
    return render(request, "management/content_list.html", {
        "title": "صفحه‌های محتوایی", "items": ContentPage.objects.all(),
        "create_url": "storefront:manager_page_create", "edit_name": "storefront:manager_page_edit", "kind": "page",
    })


@manager_required("storefront.manage_store_content")
def content_page_edit(request, pk=None):
    obj = get_object_or_404(ContentPage, pk=pk) if pk else None
    form = ContentPageForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        _audit(request, "content.page_saved", "ContentPage", saved.pk, {"slug": saved.slug, "published": saved.is_published})
        messages.success(request, "صفحه ذخیره شد.")
        return redirect("storefront:manager_pages")
    return render(request, "management/simple_form.html", {"form": form, "title": "صفحهٔ محتوایی", "back_url": "storefront:manager_pages"})


@manager_required("storefront.manage_store_content")
def faqs(request):
    return render(request, "management/content_list.html", {
        "title": "پرسش‌های پرتکرار", "items": FAQ.objects.all(),
        "create_url": "storefront:manager_faq_create", "edit_name": "storefront:manager_faq_edit", "kind": "faq",
    })


@manager_required("storefront.manage_store_content")
def faq_edit(request, pk=None):
    obj = get_object_or_404(FAQ, pk=pk) if pk else None
    form = FAQForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        _audit(request, "content.faq_saved", "FAQ", saved.pk, {"question": saved.question, "published": saved.is_published})
        messages.success(request, "پرسش ذخیره شد.")
        return redirect("storefront:manager_faqs")
    return render(request, "management/simple_form.html", {"form": form, "title": "پرسش پرتکرار", "back_url": "storefront:manager_faqs"})


@manager_required("commerce.manage_promotions")
def coupons(request):
    return render(request, "management/content_list.html", {
        "title": "کدهای تخفیف", "items": Coupon.objects.all(),
        "create_url": "storefront:manager_coupon_create", "edit_name": "storefront:manager_coupon_edit", "kind": "coupon",
    })


@manager_required("commerce.manage_promotions")
def coupon_edit(request, pk=None):
    obj = get_object_or_404(Coupon, pk=pk) if pk else None
    form = CouponForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        _audit(request, "promotion.coupon_saved", "Coupon", saved.pk, {"code": saved.code, "active": saved.is_active})
        messages.success(request, "کد تخفیف ذخیره شد.")
        return redirect("storefront:manager_coupons")
    return render(request, "management/simple_form.html", {"form": form, "title": "کد تخفیف", "back_url": "storefront:manager_coupons"})


@manager_required("commerce.view_financial_reports")
def audit_log(request):
    events = AuditLog.objects.select_related("actor").all()
    page = Paginator(events, 50).get_page(request.GET.get("page"))
    return render(request, "management/audit.html", {"page_obj": page, "events": page.object_list})


@manager_required("catalog.manage_products")
def digital_list(request):
    products = Product.objects.filter(product_type=Product.ProductType.DIGITAL).select_related("category").annotate(
        file_count=Count("assets", distinct=True), downloads=Sum("assets__download_count"),
    )
    query = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    if status in Product.Status.values:
        products = products.filter(status=status)
    return render(request, "management/digital_products.html", {
        "free_products": products.filter(is_free=True).order_by("-created_at"),
        "paid_products": products.filter(is_free=False).order_by("-created_at"),
        "query": query, "status": status, "product_statuses": Product.Status.choices,
    })


@manager_required("catalog.manage_products")
def digital_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk, product_type=Product.ProductType.DIGITAL) if pk else None
    form = DigitalProductForm(request.POST or None, request.FILES or None, instance=product)
    assets = DigitalAssetFormSet(request.POST or None, request.FILES or None, instance=product, prefix="assets")
    if request.method == "POST" and form.is_valid() and assets.is_valid():
        with transaction.atomic():
            created = product is None
            product = form.save()
            assets.instance = product
            assets.save()
            if product.status == Product.Status.PUBLISHED and not product.assets.filter(is_active=True).exists():
                product.status = Product.Status.DRAFT
                product.save(update_fields=("status", "updated_at"))
                messages.warning(request, "بدون فایل فعال امکان انتشار نیست؛ محصول به پیش‌نویس برگشت.")
            _audit(request, "digital_product.created" if created else "digital_product.updated", "Product", product.pk,
                   {"name": product.name, "free": product.is_free, "status": product.status})
        messages.success(request, "محصول دیجیتال ذخیره شد.")
        return redirect("storefront:manager_digital_edit", pk=product.pk)
    return render(request, "management/digital_form.html", {"form": form, "assets": assets, "product": product})
