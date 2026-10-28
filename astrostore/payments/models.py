from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from commerce.models import Order


class PaymentTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار شروع"
        INITIATING = "initiating", "در حال ارتباط با درگاه"
        INITIATION_FAILED = "initiation_failed", "شروع ناموفق"
        AWAITING_VERIFICATION = "awaiting_verification", "در انتظار تأیید"
        VERIFYING = "verifying", "در حال تأیید"
        EXPIRED = "expired", "مهلت پرداخت پایان‌یافته"
        PAID = "paid", "پرداخت موفق"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغوشده"
        REFUNDED = "refunded", "بازپرداخت‌شده"
        PARTIALLY_REFUNDED = "partially_refunded", "بازپرداخت جزئی"
        REVIEW = "review", "نیازمند بررسی"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=30, default="zarinpal")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    amount_toman = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    amount_rial = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    authority = models.CharField(max_length=100, unique=True, null=True, blank=True)
    reference_id = models.CharField(max_length=100, blank=True, db_index=True)
    provider_code = models.CharField(max_length=20, blank=True)
    provider_message = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("order", "created_at")), models.Index(fields=("status", "created_at"))]
        constraints = [models.UniqueConstraint(fields=("order",), name="one_payment_transaction_per_order")]
        permissions = [("manage_refunds", "Can manage and reconcile refunds")]

    def __str__(self):
        return f"{self.order.order_number} — {self.get_status_display()}"


class RefundRecord(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "درخواست‌شده"
        SUBMITTED = "submitted", "در انتظار تسویه"
        CONFIRMED = "confirmed", "تأییدشده"
        FAILED = "failed", "ناموفق"

    payment = models.ForeignKey(PaymentTransaction, on_delete=models.PROTECT, related_name="refunds")
    amount_toman = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=300)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    external_reference = models.CharField(max_length=120, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="refund_requests")
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="refund_reconciliations")
    created_at = models.DateTimeField(auto_now_add=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
