from django.contrib import admin

from .models import AuditLog, ContentPage, FAQ, HeroBanner, HomeSection, ShippingRate, StoreSettings


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ("store_name", "currency_label", "updated_at")
    readonly_fields = ("created_at", "updated_at")


admin.site.register((ShippingRate, HeroBanner, HomeSection, ContentPage, FAQ))


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "object_type", "object_id", "actor", "created_at")
    list_filter = ("object_type", "created_at")
    search_fields = ("action", "object_id")
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

