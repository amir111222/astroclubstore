import re

from django import forms
from django.core.exceptions import ValidationError

from .models import Address, User
from .phone import normalize_digits, normalize_phone


class PhoneForm(forms.Form):
    phone_number = forms.CharField(
        label="شمارهٔ همراه", max_length=11, min_length=11,
        widget=forms.TextInput(attrs={
            "type": "tel", "inputmode": "numeric", "autocomplete": "tel-national", "dir": "ltr",
            "placeholder": "09121234567", "maxlength": "11", "pattern": "09[0-9]{9}",
            "data-phone-input": "", "required": "required",
        }),
    )
    remember_me = forms.BooleanField(label="ورود من را به خاطر بسپار", required=False, initial=True)

    def clean_phone_number(self):
        raw = normalize_digits(self.cleaned_data["phone_number"]).strip()
        if not re.fullmatch(r"09\d{9}", raw):
            raise ValidationError("شماره را به شکل ۰۹۱۲۱۲۳۴۵۶۷ وارد کنید.")
        try:
            # "09121234567" -> "+989121234567"
            return normalize_phone("+98" + raw[1:])
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class OTPForm(forms.Form):
    code = forms.CharField(
        label="کد یک‌بارمصرف",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
            "pattern": "[0-9۰-۹٠-٩]{6}",
        }),
    )

    def clean_code(self):
        value = normalize_digits(self.cleaned_data["code"])
        if not value.isdigit():
            raise ValidationError("کد باید شامل شش رقم باشد.")
        return value


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        labels = {"first_name": "نام", "last_name": "نام خانوادگی", "email": "ایمیل"}


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        exclude = ("user",)
        labels = {
            "recipient_name": "نام گیرنده", "recipient_phone": "تلفن گیرنده",
            "province": "استان", "city": "شهر", "postal_code": "کد پستی",
            "address": "نشانی کامل", "details": "جزئیات تکمیلی", "is_default": "نشانی پیش‌فرض",
        }
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "details": forms.TextInput()}

    def clean_recipient_phone(self):
        try:
            return normalize_phone(self.cleaned_data["recipient_phone"])
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def clean_postal_code(self):
        code = normalize_digits(self.cleaned_data["postal_code"])
        if len(code) != 10 or not code.isdigit():
            raise ValidationError("کد پستی باید ده رقم باشد.")
        return code


class AccountDeletionForm(forms.Form):
    reason = forms.CharField(label="توضیح (اختیاری)", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
