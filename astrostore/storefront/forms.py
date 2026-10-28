from django import forms

from commerce.models import Coupon
from payments.models import RefundRecord
from .models import ContentPage, FAQ, HeroBanner, HomeSection, ShippingRate, StoreSettings


class StoreSettingsForm(forms.ModelForm):
    class Meta:
        model = StoreSettings
        fields = (
            "store_name", "logo", "favicon", "contact_email", "contact_phone", "contact_address", "social_links",
            "currency_label", "default_shipping_toman", "free_shipping_threshold_toman", "tax_enabled",
            "tax_rate_percent", "shipping_is_taxable", "announcement_text", "announcement_active",
        )
        labels = {
            "store_name": "نام فروشگاه", "logo": "نشان فروشگاه", "favicon": "آیکن مرورگر",
            "contact_email": "ایمیل تماس", "contact_phone": "تلفن تماس", "contact_address": "نشانی تماس",
            "social_links": "پیوند شبکه‌های اجتماعی (JSON)", "currency_label": "واحد پول نمایشی",
            "default_shipping_toman": "هزینهٔ پیش‌فرض ارسال (تومان)", "free_shipping_threshold_toman": "حد ارسال رایگان (تومان)",
            "tax_enabled": "محاسبهٔ مالیات فعال باشد", "tax_rate_percent": "نرخ مالیات (%)",
            "shipping_is_taxable": "هزینهٔ ارسال مشمول مالیات باشد", "announcement_text": "متن نوار اعلان",
            "announcement_active": "نمایش نوار اعلان",
        }
        widgets = {"social_links": forms.Textarea(attrs={"rows": 3, "dir": "ltr"}), "contact_address": forms.Textarea(attrs={"rows": 2})}


class ShippingRateForm(forms.ModelForm):
    class Meta:
        model = ShippingRate
        fields = ("name", "province", "city", "charge_toman", "free_threshold_toman", "is_enabled", "position")
        labels = {"name": "روش ارسال", "province": "استان (اختیاری)", "city": "شهر (اختیاری)", "charge_toman": "هزینه (تومان)", "free_threshold_toman": "حد ارسال رایگان (تومان)", "is_enabled": "فعال", "position": "ترتیب"}


class BannerForm(forms.ModelForm):
    class Meta:
        model = HeroBanner
        fields = ("title", "description", "image", "image_alt", "cta_text", "cta_url", "position", "is_active", "starts_at", "ends_at")
        labels = {"title": "عنوان", "description": "توضیح", "image": "تصویر بنر", "image_alt": "متن جایگزین", "cta_text": "متن دکمه", "cta_url": "پیوند دکمه", "position": "ترتیب", "is_active": "فعال", "starts_at": "شروع نمایش", "ends_at": "پایان نمایش"}
        widgets = {"description": forms.Textarea(attrs={"rows": 2}), "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}


class HomeSectionForm(forms.ModelForm):
    class Meta:
        model = HomeSection
        fields = ("title", "kind", "category", "products", "position", "is_visible")
        labels = {"title": "عنوان بخش", "kind": "نوع بخش", "category": "دسته", "products": "محصولات انتخابی", "position": "ترتیب", "is_visible": "نمایش"}


class ContentPageForm(forms.ModelForm):
    class Meta:
        model = ContentPage
        fields = ("slug", "title", "body", "meta_description", "is_published")
        labels = {"slug": "نشانی", "title": "عنوان صفحه", "body": "متن ساده", "meta_description": "توضیح متا", "is_published": "منتشرشده"}
        widgets = {"body": forms.Textarea(attrs={"rows": 12}), "meta_description": forms.Textarea(attrs={"rows": 2})}


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ("question", "answer", "position", "is_published")
        labels = {"question": "پرسش", "answer": "پاسخ", "position": "ترتیب", "is_published": "نمایش"}
        widgets = {"answer": forms.Textarea(attrs={"rows": 4})}


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ("code", "discount_type", "value", "maximum_discount_toman", "minimum_purchase_toman", "starts_at", "ends_at", "usage_limit", "per_customer_limit", "eligible_products", "eligible_categories", "is_active")
        labels = {"code": "کد", "discount_type": "نوع تخفیف", "value": "مقدار/درصد", "maximum_discount_toman": "سقف تخفیف (تومان)", "minimum_purchase_toman": "حداقل خرید (تومان)", "starts_at": "شروع", "ends_at": "پایان", "usage_limit": "سقف کل استفاده", "per_customer_limit": "سقف استفاده برای هر مشتری", "eligible_products": "محصولات مشمول", "eligible_categories": "دسته‌های مشمول", "is_active": "فعال"}
        widgets = {"starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class RefundRequestForm(forms.ModelForm):
    class Meta:
        model = RefundRecord
        fields = ("amount_toman", "reason")
        labels = {"amount_toman": "مبلغ بازپرداخت (تومان)", "reason": "دلیل"}


class RefundReconcileForm(forms.Form):
    status = forms.ChoiceField(label="وضعیت تسویه", choices=((RefundRecord.Status.SUBMITTED, "ثبت برای تسویه"), (RefundRecord.Status.CONFIRMED, "تأیید تسویه"), (RefundRecord.Status.FAILED, "ناموفق")))
    external_reference = forms.CharField(label="شناسه/رسید بیرونی", max_length=120, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") in (RefundRecord.Status.SUBMITTED, RefundRecord.Status.CONFIRMED) and not cleaned.get("external_reference", "").strip():
            self.add_error("external_reference", "برای ثبت تسویه، شناسه یا رسید بیرونی لازم است.")
        return cleaned
