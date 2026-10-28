from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from urllib.parse import urlsplit

from catalog.models import Category, Product
from catalog.validators import validate_image_upload


class StoreSettings(models.Model):
    singleton_key = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    store_name = models.CharField("نام فروشگاه", max_length=120, default="نام فروشگاه")
    logo = models.FileField(upload_to="store/", blank=True, validators=[validate_image_upload])
    favicon = models.FileField(upload_to="store/", blank=True, validators=[validate_image_upload])
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    contact_address = models.CharField(max_length=300, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    currency_label = models.CharField(max_length=20, default="تومان")
    default_shipping_toman = models.PositiveBigIntegerField(default=0)
    free_shipping_threshold_toman = models.PositiveBigIntegerField(null=True, blank=True)
    tax_enabled = models.BooleanField(default=False)
    tax_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    shipping_is_taxable = models.BooleanField(default=False)
    announcement_text = models.CharField(max_length=240, blank=True)
    announcement_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیم فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"
        permissions = [
            ("manage_store_settings", "Can manage store settings"),
            ("manage_store_content", "Can manage storefront content"),
            ("view_store_dashboard", "Can view store dashboard"),
        ]

    def clean(self):
        super().clean()
        if self.tax_rate_percent > 100:
            raise ValidationError({"tax_rate_percent": "نرخ مالیات باید بین صفر تا صد باشد."})
        if not isinstance(self.social_links, dict):
            raise ValidationError({"social_links": "پیوندهای اجتماعی باید یک شیء JSON با نام و نشانی باشند."})
        for label, target in self.social_links.items():
            parsed = urlsplit(target) if isinstance(target, str) else None
            if not isinstance(label, str) or not parsed or parsed.scheme != "https" or not parsed.netloc:
                raise ValidationError({"social_links": "همهٔ نشانی‌های اجتماعی باید پیوند HTTPS معتبر باشند."})
        if self.pk and StoreSettings.objects.exclude(pk=self.pk).exists():
            raise ValidationError("تنظیم فروشگاه فقط یک رکورد دارد.")

    @classmethod
    def get_solo(cls):
        settings_obj, _ = cls.objects.get_or_create(singleton_key=1)
        return settings_obj


class ShippingRate(models.Model):
    name = models.CharField(max_length=100, default="پست ایران")
    province = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    charge_toman = models.PositiveBigIntegerField(default=0)
    free_threshold_toman = models.PositiveBigIntegerField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "province", "city", "id")

    def __str__(self):
        destination = "، ".join(value for value in (self.province, self.city) if value)
        return f"{self.name}{f' — {destination}' if destination else ''}"


class HeroBanner(models.Model):
    title = models.CharField(max_length=140)
    description = models.CharField(max_length=300, blank=True)
    image = models.FileField(upload_to="banners/%Y/%m/", validators=[validate_image_upload])
    image_alt = models.CharField(max_length=180, blank=True)
    cta_text = models.CharField(max_length=60, blank=True)
    cta_url = models.CharField(max_length=300, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "id")

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "پایان نمایش باید بعد از شروع باشد."})
        if self.cta_url and not (
            (self.cta_url.startswith("/") and not self.cta_url.startswith("//") and "\\" not in self.cta_url)
            or (self.cta_url.startswith("https://") and bool(urlsplit(self.cta_url).netloc))
        ):
            raise ValidationError({"cta_url": "پیوند باید داخلی یا با HTTPS باشد."})

    @classmethod
    def active(cls):
        now = timezone.now()
        return cls.objects.filter(is_active=True).filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now)).filter(
            models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now)
        )


class HomeSection(models.Model):
    class Kind(models.TextChoices):
        FEATURED = "featured", "محصولات ویژه"
        NEW = "new", "تازه‌واردها"
        BESTSELLER = "bestseller", "پرفروش‌ها"
        DISCOUNT = "discount", "پیشنهادها"
        CATEGORY = "category", "دسته‌بندی"

    title = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="homepage_sections")
    products = models.ManyToManyField(Product, blank=True, related_name="homepage_sections")
    position = models.PositiveSmallIntegerField(default=0)
    is_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ("position", "id")


class ContentPage(models.Model):
    slug = models.SlugField(unique=True, allow_unicode=True, max_length=140)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True, help_text="متن ساده؛ خروجی با escaping امن نمایش داده می‌شود.")
    meta_description = models.CharField(max_length=300, blank=True)
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title",)


class FAQ(models.Model):
    question = models.CharField(max_length=240)
    answer = models.TextField()
    position = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ("position", "id")


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("object_type", "object_id", "created_at"))]
