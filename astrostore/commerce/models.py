import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from account.models import Address
from catalog.models import Category, Product, ProductVariant


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="cart")
    guest_token = models.UUIDField(null=True, blank=True, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=(Q(user__isnull=False, guest_token__isnull=True) | Q(user__isnull=True, guest_token__isnull=False)),
            name="cart_has_exactly_one_owner",
        )]


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="cart_items")
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT, related_name="cart_items")
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_item_positive_quantity"),
            models.UniqueConstraint(fields=("cart", "product"), condition=Q(variant__isnull=True), name="unique_cart_simple_product"),
            models.UniqueConstraint(fields=("cart", "product", "variant"), condition=Q(variant__isnull=False), name="unique_cart_product_variant"),
        ]


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlists")
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.CASCADE, related_name="wishlists")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("user", "product"), condition=Q(variant__isnull=True), name="unique_wishlist_simple_product"),
            models.UniqueConstraint(fields=("user", "product", "variant"), condition=Q(variant__isnull=False), name="unique_wishlist_product_variant"),
        ]


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "درصدی"
        FIXED = "fixed", "مبلغ ثابت"

    code = models.CharField(max_length=40, unique=True)
    discount_type = models.CharField(max_length=8, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(0)])
    maximum_discount_toman = models.PositiveBigIntegerField(null=True, blank=True)
    minimum_purchase_toman = models.PositiveBigIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    per_customer_limit = models.PositiveSmallIntegerField(default=1)
    eligible_products = models.ManyToManyField(Product, blank=True, related_name="coupons")
    eligible_categories = models.ManyToManyField(Category, blank=True, related_name="coupons")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        permissions = [("manage_promotions", "Can manage promotions")]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.discount_type == self.DiscountType.PERCENT and self.value > 100:
            raise ValidationError({"value": "درصد تخفیف نمی‌تواند بیش از ۱۰۰ باشد."})
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "پایان تخفیف باید بعد از شروع آن باشد."})

    def __str__(self):
        return self.code


class Order(models.Model):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "در انتظار پرداخت"
        PROCESSING = "processing", "در حال آماده‌سازی"
        PACKED = "packed", "بسته‌بندی‌شده"
        SHIPPED = "shipped", "ارسال‌شده"
        DELIVERED = "delivered", "تحویل‌شده"
        CANCEL_REQUESTED = "cancel_requested", "درخواست لغو"
        CANCELLED = "cancelled", "لغوشده"
        PAYMENT_REVIEW = "payment_review", "نیازمند بررسی پرداخت"
        REFUNDED = "refunded", "بازپرداخت‌شده"

    order_number = models.CharField(max_length=32, unique=True, db_index=True)
    checkout_key = models.UUIDField(default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.AWAITING_PAYMENT, db_index=True)
    address_snapshot = models.JSONField(default=dict)
    shipping_method_label = models.CharField(max_length=120, default="پست ایران")
    shipping_tracking_number = models.CharField(max_length=120, blank=True)
    subtotal_toman = models.PositiveBigIntegerField(default=0)
    item_discount_toman = models.PositiveBigIntegerField(default=0)
    coupon_discount_toman = models.PositiveBigIntegerField(default=0)
    shipping_toman = models.PositiveBigIntegerField(default=0)
    tax_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_toman = models.PositiveBigIntegerField(default=0)
    taxable_base_toman = models.PositiveBigIntegerField(default=0)
    total_toman = models.PositiveBigIntegerField(default=0)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    stock_reserved = models.BooleanField(default=False)
    reservation_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    placed_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_digital_only(self):
        items = list(self.items.all())
        return bool(items) and all(i.is_digital for i in items)

    @property
    def downloads_open(self):
        return self.status in (self.Status.PROCESSING, self.Status.PACKED, self.Status.SHIPPED, self.Status.DELIVERED)

    class Meta:
        ordering = ("-placed_at",)
        indexes = [models.Index(fields=("user", "placed_at")), models.Index(fields=("status", "placed_at"))]
        constraints = [
            models.UniqueConstraint(fields=("user", "checkout_key"), name="unique_checkout_request_per_user"),
            models.CheckConstraint(condition=Q(total_toman__gte=0), name="order_total_nonnegative"),
        ]
        permissions = [("manage_orders", "Can manage orders"), ("view_financial_reports", "Can view financial reports")]

    @property
    def discount_total_toman(self):
        return self.item_discount_toman + self.coupon_discount_toman

    @property
    def payment(self):
        return self.payments.order_by("-created_at").first()

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="order_items")
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.SET_NULL, related_name="order_items")
    cart_item_ref = models.PositiveBigIntegerField(null=True, blank=True)
    product_name = models.CharField(max_length=180)
    sku = models.CharField(max_length=64)
    variant_name = models.CharField(max_length=100, blank=True)
    image_snapshot = models.CharField(max_length=500, blank=True)
    is_digital = models.BooleanField(default=False)
    download_count = models.PositiveIntegerField(default=0)
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    regular_unit_toman = models.PositiveBigIntegerField()
    sale_unit_toman = models.PositiveBigIntegerField()
    item_discount_toman = models.PositiveBigIntegerField(default=0)
    line_total_toman = models.PositiveBigIntegerField()

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=1), name="order_item_positive_quantity")]


class CouponRedemption(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "رزروشده"
        REDEEMED = "redeemed", "مصرف‌شده"
        CANCELLED = "cancelled", "آزادشده"

    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="redemptions")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="coupon_redemption")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="coupon_redemptions")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)


class OrderEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=24, choices=Order.Status.choices)
    message = models.CharField(max_length=300)
    is_public = models.BooleanField(default=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class CancellationRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "درخواست‌شده"
        APPROVED = "approved", "تأییدشده"
        REJECTED = "rejected", "ردشده"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="cancellation_request")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cancellation_requests")
    previous_order_status = models.CharField(max_length=24, choices=Order.Status.choices, blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    reason = models.CharField(max_length=300, blank=True)
    manager_note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
