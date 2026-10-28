from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from commerce.models import CouponRedemption, Order, OrderEvent
from commerce.services import cancel_unpaid_order, clear_ordered_cart
from storefront.models import AuditLog

from .gateways import GatewayError, request_payment, verify_payment
from .models import PaymentTransaction


def create_transaction(order):
    multiplier = int(getattr(settings, "ZARINPAL_TOMAN_TO_RIAL", 10))
    if multiplier < 1:
        raise ValueError("ZARINPAL_TOMAN_TO_RIAL must be a positive integer.")
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        payment = PaymentTransaction.objects.filter(order=locked_order).first()
        if payment:
            return payment
        return PaymentTransaction.objects.create(
            order=locked_order,
            amount_toman=locked_order.total_toman,
            amount_rial=locked_order.total_toman * multiplier,
        )


def _payment_url(authority):
    return getattr(settings, "ZARINPAL_PAYMENT_BASE_URL", "https://www.zarinpal.com/pg/StartPay/") + authority


def initiate_payment(payment, request):
    with transaction.atomic():
        current = PaymentTransaction.objects.select_for_update().select_related("order").get(pk=payment.pk)
        if current.status == PaymentTransaction.Status.AWAITING_VERIFICATION and current.authority:
            return _payment_url(current.authority)
        if current.status != PaymentTransaction.Status.PENDING:
            raise GatewayError("درخواست پرداخت برای این سفارش قابل تکرار نیست.")
        current.status = PaymentTransaction.Status.INITIATING
        current.save(update_fields=("status", "updated_at"))
        order = current.order
    callback_url = request.build_absolute_uri(reverse("payments:callback"))
    try:
        authority = request_payment(
            amount_rial=payment.amount_rial,
            description=f"سفارش {order.order_number}",
            callback_url=callback_url,
            mobile=order.user.phone_number,
        )
    except GatewayError:
        with transaction.atomic():
            current = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
            current.status = PaymentTransaction.Status.INITIATION_FAILED
            current.provider_message = "درخواست پرداخت ثبت نشد."
            current.save(update_fields=("status", "provider_message", "updated_at"))
        cancel_unpaid_order(order, message="پرداخت آغاز نشد.")
        raise
    with transaction.atomic():
        current = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
        current.authority = authority
        current.status = PaymentTransaction.Status.AWAITING_VERIFICATION
        current.save(update_fields=("authority", "status", "updated_at"))
    return _payment_url(authority)


def _mark_review(payment_id, message, code=""):
    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().select_related("order").get(pk=payment_id)
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        if payment.status == PaymentTransaction.Status.PAID:
            return order, "paid"
        payment.status = PaymentTransaction.Status.REVIEW
        payment.provider_code = str(code)[:20]
        payment.provider_message = message[:200]
        payment.save(update_fields=("status", "provider_code", "provider_message", "updated_at"))
        if order.status != Order.Status.PAYMENT_REVIEW:
            order.status = Order.Status.PAYMENT_REVIEW
            order.save(update_fields=("status", "updated_at"))
            OrderEvent.objects.create(order=order, status=order.status, message=message[:300], is_public=True)
        return order, "review"


def handle_callback(authority, status):
    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().select_related("order").filter(authority=authority).first()
        if payment is None:
            return None, "unknown"
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        if payment.status == PaymentTransaction.Status.PAID:
            return order, "paid"
        if payment.status == PaymentTransaction.Status.VERIFYING:
            return order, "review"
        if status.upper() != "OK":
            payment.status = PaymentTransaction.Status.CANCELLED
            payment.provider_code = "callback_not_ok"
            payment.provider_message = "درگاه بازگشت ناموفق را گزارش کرد."
            payment.save(update_fields=("status", "provider_code", "provider_message", "updated_at"))
            should_cancel = order.status == Order.Status.AWAITING_PAYMENT
            payment_id = payment.pk
        elif payment.status in (
            PaymentTransaction.Status.AWAITING_VERIFICATION,
            PaymentTransaction.Status.EXPIRED,
            PaymentTransaction.Status.REVIEW,
            PaymentTransaction.Status.CANCELLED,
        ):
            payment.status = PaymentTransaction.Status.VERIFYING
            payment.save(update_fields=("status", "updated_at"))
            payment_id = payment.pk
            amount_rial = payment.amount_rial
            saved_amount_toman = payment.amount_toman
            order_id = order.pk
            should_cancel = False
        else:
            return order, payment.status
    if status.upper() != "OK":
        if should_cancel:
            cancel_unpaid_order(order, "درگاه پرداخت سفارش را لغو کرد.")
            order.refresh_from_db()
        return order, "cancelled"
    try:
        result = verify_payment(amount_rial=amount_rial, authority=authority)
    except GatewayError:
        return _mark_review(payment_id, "تأیید پرداخت از درگاه در دسترس نبود.")
    code = result["code"]
    if code == "100" and result["ref_id"]:
        order_paid_for_fulfillment = False
        with transaction.atomic():
            payment = PaymentTransaction.objects.select_for_update().get(pk=payment_id)
            order = Order.objects.select_for_update().get(pk=order_id)
            if payment.status == PaymentTransaction.Status.PAID:
                return order, "paid"
            amount_matches = payment.amount_toman == order.total_toman == saved_amount_toman
            payment.reference_id = result["ref_id"][:100]
            payment.provider_code = code
            payment.provider_message = "پرداخت در سمت درگاه تأیید شد."
            payment.verified_at = timezone.now()
            payment.status = PaymentTransaction.Status.PAID if amount_matches else PaymentTransaction.Status.REVIEW
            if not amount_matches:
                payment.provider_message = "مبلغ سفارش با تراکنش تطبیق ندارد و نیازمند بررسی است."
            payment.save(update_fields=("reference_id", "provider_code", "provider_message", "verified_at", "status", "updated_at"))
            if amount_matches and order.status == Order.Status.AWAITING_PAYMENT and order.stock_reserved:
                digital_only = order.is_digital_only
                order.status = Order.Status.DELIVERED if digital_only else Order.Status.PROCESSING
                order.stock_reserved = False
                order.reservation_expires_at = None
                order_paid_for_fulfillment = True
                order.save(update_fields=("status", "stock_reserved", "reservation_expires_at", "updated_at"))
                CouponRedemption.objects.filter(order=order, status=CouponRedemption.Status.PENDING).update(
                    status=CouponRedemption.Status.REDEEMED, redeemed_at=timezone.now()
                )
                event = ("پرداخت تأیید شد و دانلود فایل‌ها فعال شد." if digital_only
                         else "پرداخت تأیید شد و سفارش برای آماده‌سازی ثبت شد.")
            else:
                order.status = Order.Status.PAYMENT_REVIEW
                order.save(update_fields=("status", "updated_at"))
                event = "پرداخت تأیید شد اما سفارش به بررسی مدیر نیاز دارد."
            OrderEvent.objects.create(order=order, status=order.status, message=event, is_public=True)
            AuditLog.objects.create(action="payment.verified", object_type="PaymentTransaction", object_id=str(payment.pk),
                                    changes={"order": order.order_number, "reference": payment.reference_id, "amount_matches": amount_matches})
        if order_paid_for_fulfillment:
            clear_ordered_cart(order)
            return order, "paid"
        return order, "review"
    if code == "101":
        return _mark_review(payment_id, "درگاه اعلام کرد تراکنش قبلاً تأیید شده است؛ تطبیق دستی لازم است.", code)
    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().get(pk=payment_id)
        if payment.status != PaymentTransaction.Status.PAID:
            payment.status = PaymentTransaction.Status.FAILED
            payment.provider_code = code[:20]
            payment.provider_message = "پرداخت توسط درگاه تأیید نشد."
            payment.save(update_fields=("status", "provider_code", "provider_message", "updated_at"))
    cancel_unpaid_order(Order.objects.get(pk=order_id), "پرداخت توسط درگاه تأیید نشد.")
    return Order.objects.get(pk=order_id), "failed"
