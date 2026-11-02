import uuid

from django import forms
from django.forms import inlineformset_factory
from django.utils.text import slugify

from .models import Category, DigitalAsset, Product, ProductImage, ProductVariant


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name", "slug", "sku", "short_description", "description", "category", "brand",
            "specifications", "image", "price_toman", "sale_price_toman",
            "low_stock_threshold", "status", "is_featured", "is_new", "is_bestseller",
        )
        labels = {
            "name": "نام محصول", "slug": "نشانی یکتا", "sku": "کد محصول", "short_description": "توضیح کوتاه",
            "description": "توضیحات", "category": "دسته", "brand": "برند", "specifications": "مشخصات (JSON)",
            "image": "تصویر اصلی", "price_toman": "قیمت به تومان", "sale_price_toman": "قیمت ویژه به تومان",
            "low_stock_threshold": "هشدار کمبود موجودی",
            "status": "وضعیت انتشار", "is_featured": "محصول ویژه", "is_new": "تازه‌وارد", "is_bestseller": "پرفروش",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "specifications": forms.Textarea(attrs={"rows": 5, "dir": "ltr"}),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        if not slug:
            slug = slugify(self.cleaned_data["name"], allow_unicode=True) or f"product-{uuid.uuid4().hex[:8]}"
        qs = Product.objects.filter(slug=slug)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این نشانی قبلاً استفاده شده است.")
        return slug


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "slug", "description", "parent", "image", "position", "is_active")
        labels = {"name": "نام دسته", "slug": "نشانی", "description": "توضیحات", "parent": "دستهٔ والد", "image": "تصویر", "position": "ترتیب", "is_active": "نمایش در فروشگاه"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.exclude(pk=self.instance.pk) if self.instance.pk else Category.objects.all()

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        if not slug:
            slug = slugify(self.cleaned_data["name"], allow_unicode=True) or f"category-{uuid.uuid4().hex[:8]}"
        return slug


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ("title", "sku", "price_override_toman", "sale_override_toman", "low_stock_threshold", "is_active")
        labels = {"title": "عنوان گونه", "sku": "کد کالا", "price_override_toman": "قیمت اختصاصی", "sale_override_toman": "قیمت ویژه", "low_stock_threshold": "آستانهٔ کمبود", "is_active": "فعال"}


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ("image", "alt_text", "position")
        labels = {"image": "تصویر", "alt_text": "متن جایگزین", "position": "ترتیب"}


ProductVariantFormSet = inlineformset_factory(Product, ProductVariant, form=ProductVariantForm, extra=1, can_delete=True)
ProductImageFormSet = inlineformset_factory(Product, ProductImage, form=ProductImageForm, extra=1, can_delete=True)


class DigitalProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ("name", "slug", "sku", "short_description", "description", "category", "image",
                  "is_free", "price_toman", "sale_price_toman", "status")
        labels = {
            "name": "نام محصول", "slug": "نشانی یکتا", "sku": "کد محصول", "short_description": "توضیح کوتاه",
            "description": "توضیحات", "category": "دسته", "image": "تصویر کاور",
            "is_free": "دانلود رایگان (بدون پرداخت)", "price_toman": "قیمت به تومان",
            "sale_price_toman": "قیمت ویژه به تومان", "status": "وضعیت انتشار",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "short_description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["price_toman"].required = False
        self.fields["price_toman"].help_text = "برای محصول رایگان لازم نیست."

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        if not slug:
            slug = slugify(self.cleaned_data.get("name", ""), allow_unicode=True) or f"digital-{uuid.uuid4().hex[:8]}"
        qs = Product.objects.filter(slug=slug)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این نشانی قبلاً استفاده شده است.")
        return slug

    def clean(self):
        data = super().clean()
        if data.get("is_free"):
            data["price_toman"] = 1
            data["sale_price_toman"] = None
        elif not data.get("price_toman"):
            self.add_error("price_toman", "برای محصول پولی قیمت لازم است.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.product_type = Product.ProductType.DIGITAL
        obj.stock_quantity = 0
        if self.cleaned_data.get("is_free"):
            obj.price_toman = 1
            obj.sale_price_toman = None
        if commit:
            obj.save()
        return obj

    def _post_clean(self):
        self.instance.product_type = Product.ProductType.DIGITAL
        if self.cleaned_data.get("is_free"):
            self.instance.price_toman = 1
        super()._post_clean()


class PrivateFileInput(forms.FileInput):
    """File input that never builds a URL, so private files can be edited safely."""

    def format_value(self, value):
        return None


class DigitalAssetForm(forms.ModelForm):
    class Meta:
        model = DigitalAsset
        fields = ("title", "file", "is_active")
        labels = {"title": "عنوان فایل", "file": "فایل", "is_active": "فعال"}
        widgets = {"file": PrivateFileInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["file"].required = False
            self.fields["file"].help_text = f"فایل فعلی: {self.instance.original_name or self.instance.file.name}. برای جایگزینی، فایل تازه انتخاب کنید."


DigitalAssetFormSet = inlineformset_factory(Product, DigitalAsset, form=DigitalAssetForm, extra=1, can_delete=True)
