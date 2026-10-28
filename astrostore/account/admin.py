from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import AccountDeletionRequest, Address, User


class AccountAddForm(forms.ModelForm):
    password1 = forms.CharField(label="گذرواژهٔ اولیه", widget=forms.PasswordInput)
    password2 = forms.CharField(label="تکرار گذرواژه", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("phone_number", "first_name", "last_name", "email", "is_active", "is_staff", "is_superuser")

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", "گذرواژه‌ها یکسان نیستند.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class AccountChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="گذرواژه")

    class Meta:
        model = User
        fields = ("phone_number", "password", "first_name", "last_name", "email", "is_active", "is_staff", "is_superuser", "groups", "user_permissions", "last_login", "date_joined")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = AccountAddForm
    form = AccountChangeForm
    model = User
    ordering = ("phone_number",)
    list_display = ("phone_number", "first_name", "last_name", "is_active", "is_staff")
    search_fields = ("phone_number", "first_name", "last_name", "email")
    readonly_fields = ("last_login", "date_joined")
    fieldsets = (
        ("حساب", {"fields": ("phone_number", "password")}),
        ("اطلاعات شخصی", {"fields": ("first_name", "last_name", "email")}),
        ("دسترسی", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("زمان‌ها", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone_number", "first_name", "last_name", "email", "password1", "password2", "is_active", "is_staff", "is_superuser")}),)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("recipient_name", "user", "province", "city", "is_default")
    search_fields = ("recipient_name", "user__phone_number", "postal_code")
    list_filter = ("province", "is_default")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AccountDeletionRequest)
class AccountDeletionAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "created_at", "resolved_at")
    list_filter = ("status",)
    readonly_fields = ("user", "reason", "created_at")
