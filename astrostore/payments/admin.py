from django.contrib import admin

from .models import PaymentTransaction, RefundRecord


@admin.register(PaymentTransaction)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "provider", "status", "amount_toman", "reference_id", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("order__order_number", "authority", "reference_id")
    readonly_fields = tuple(field.name for field in PaymentTransaction._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RefundRecord)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("payment", "amount_toman", "status", "requested_by", "created_at")
    list_filter = ("status",)
    readonly_fields = tuple(field.name for field in RefundRecord._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

