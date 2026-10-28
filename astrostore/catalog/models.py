from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from .storage import PrivateMediaStorage, digital_upload_to
from .validators import validate_digital_upload, validate_image_upload


class Category(models.Model):
    name = models.CharField("نام دسته", max_length=120)
    slug = models.SlugField("نشانی", max_length=150, unique=True, allow_unicode=True)
    description = models.TextField("توضیحات", blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    image = models.FileField("تصویر دسته", upload_to="categories/%Y/%m/", blank=True, validators=[validate_image_upload])
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField("نمایش در فروشگاه", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "name")
        permissions = [("manage_categories", "Can manage categories")]

    def clean(self):
        super().clean()
        node = self.parent
        while node is not None:
            if node.pk == self.pk:
                raise ValidationError({"parent": "دسته نمی‌تواند والد خودش یا یکی از زیرشاخه‌هایش باشد."})
            node = node.parent

    def __str__(self):
        return self.name


class Product(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"
        ARCHIVED = "archived", "بایگانی‌شده"

    class ProductType(models.TextChoices):
        PHYSICAL = "physical", "کالای فیزیکی"
        DIGITAL = "digital", "محصول دیجیتال (دانلودی)"

    product_type = models.CharField("نوع محصول", max_length=10, choices=ProductType.choices, default=ProductType.PHYSICAL, db_index=True)
    is_free = models.BooleanField("دانلود رایگان", default=False, db_index=True)
    name = models.CharField("نام محصول", max_length=180)
    slug = models.SlugField("نشانی", max_length=200, unique=True, allow_unicode=True)
    sku = models.CharField("کد محصول", max_length=64, unique=True)
    short_description = models.CharField("توضیح کوتاه", max_length=300, blank=True)
    description = models.TextField("توضیحات کامل", blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT, related_name="products")
    brand = models.CharField("برند", max_length=100, blank=True)
    specifications = models.JSONField("مشخصات", default=dict, blank=True)
    image = models.FileField("تصویر اصلی", upload_to="products/%Y/%m/", blank=True, validators=[validate_image_upload])
    price_toman = models.PositiveBigIntegerField("قیمت (تومان)", validators=[MinValueValidator(1)])
    sale_price_toman = models.PositiveBigIntegerField("قیمت فروش ویژه (تومان)", null=True, blank=True, validators=[MinValueValidator(1)])
    stock_quantity = models.PositiveIntegerField("موجودی", default=0)
    low_stock_threshold = models.PositiveIntegerField("آستانهٔ کمبود موجودی", default=3)
    status = models.CharField("وضعیت انتشار", max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_featured = models.BooleanField("ویژه", default=False)
    is_new = models.BooleanField("تازه‌وارد", default=False)
    is_bestseller = models.BooleanField("پرفروش", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("status", "category", "created_at")), models.Index(fields=("status", "price_toman"))]
        permissions = [("manage_products", "Can manage products"), ("manage_inventory", "Can manage inventory")]

    def clean(self):
        super().clean()
        if self.sale_price_toman is not None and self.sale_price_toman >= self.price_toman:
            raise ValidationError({"sale_price_toman": "قیمت ویژه باید کمتر از قیمت اصلی باشد."})
        if self.is_free and self.product_type != self.ProductType.DIGITAL:
            raise ValidationError({"is_free": "فقط محصول دیجیتال می‌تواند رایگان باشد."})

    @property
    def has_variants(self):
        return self.variants.exists()

    @property
    def available_price_toman(self):
        return self.sale_price_toman if self.sale_price_toman is not None else self.price_toman

    @property
    def is_digital(self):
        return self.product_type == self.ProductType.DIGITAL

    @property
    def available_stock(self):
        if self.is_digital:
            return 1 if self.assets.filter(is_active=True).exists() else 0
        if self.has_variants:
            return sum(v.stock_quantity for v in self.variants.filter(is_active=True))
        return self.stock_quantity

    @property
    def is_available(self):
        return self.status == self.Status.PUBLISHED and self.available_stock > 0

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gallery")
    image = models.FileField(upload_to="products/gallery/%Y/%m/", validators=[validate_image_upload])
    alt_text = models.CharField(max_length=180, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    title = models.CharField("عنوان گونه", max_length=100)
    sku = models.CharField("کد گونه", max_length=64, unique=True)
    price_override_toman = models.PositiveBigIntegerField("قیمت (اختیاری)", null=True, blank=True, validators=[MinValueValidator(1)])
    sale_override_toman = models.PositiveBigIntegerField("قیمت ویژه (اختیاری)", null=True, blank=True, validators=[MinValueValidator(1)])
    stock_quantity = models.PositiveIntegerField("موجودی", default=0)
    low_stock_threshold = models.PositiveIntegerField("آستانهٔ کمبود موجودی", default=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)

    def clean(self):
        super().clean()
        price = self.price_override_toman or (self.product.price_toman if self.product_id else None)
        sale = self.sale_override_toman or (self.product.sale_price_toman if self.product_id else None)
        if sale is not None and price is not None and sale >= price:
            raise ValidationError({"sale_override_toman": "قیمت ویژه باید از قیمت اصلی کمتر باشد."})

    @property
    def current_price_toman(self):
        if self.sale_override_toman is not None:
            return self.sale_override_toman
        if self.product.sale_price_toman is not None:
            return self.product.sale_price_toman
        if self.price_override_toman is not None:
            return self.price_override_toman
        return self.product.price_toman

    @property
    def regular_price_toman(self):
        return self.price_override_toman if self.price_override_toman is not None else self.product.price_toman

    def __str__(self):
        return f"{self.product.name} — {self.title}"


class InventoryMovement(models.Model):
    class Reason(models.TextChoices):
        ADJUSTMENT = "adjustment", "اصلاح موجودی"
        RESERVATION = "reservation", "رزرو سفارش"
        RELEASE = "release", "آزادسازی رزرو"
        RETURN = "return", "مرجوعی"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="inventory_movements")
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT, related_name="inventory_movements")
    delta = models.IntegerField("تغییر موجودی")
    reason = models.CharField(max_length=16, choices=Reason.choices)
    note = models.CharField(max_length=300, blank=True)
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("product", "created_at"))]


class DigitalAsset(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="assets")
    title = models.CharField("عنوان فایل", max_length=160)
    file = models.FileField("فایل", upload_to=digital_upload_to, storage=PrivateMediaStorage(), validators=[validate_digital_upload], max_length=255)
    original_name = models.CharField(max_length=255, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    download_count = models.PositiveIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)

    def save(self, *args, **kwargs):
        if self.file and not getattr(self.file, "_committed", True):
            upload = self.file.file
            self.original_name = (getattr(upload, "name", "") or self.file.name).replace("\\", "/").split("/")[-1][:255]
            self.size_bytes = getattr(upload, "size", 0) or 0
            import hashlib
            digest = hashlib.sha256()
            upload.seek(0)
            for chunk in iter(lambda: upload.read(1024 * 1024), b""):
                digest.update(chunk)
            upload.seek(0)
            self.checksum_sha256 = digest.hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} — {self.title}"
