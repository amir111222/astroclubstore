from django.contrib import admin

from .models import Cart, CartItem, CancellationRequest, Coupon, CouponRedemption, Order, OrderEvent, OrderItem, WishlistItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = tuple(field.name for field in OrderItem._meta.fields)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "status", "total_toman", "placed_at")
    list_filter = ("status", "placed_at")
    search_fields = ("order_number", "user__phone_number")
    inlines = (OrderItemInline,)
    readonly_fields = tuple(field.name for field in Order._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "value", "is_active", "ends_at")
    list_filter = ("discount_type", "is_active")
    search_fields = ("code",)


@admin.register(CancellationRequest)
class CancellationRequestAdmin(admin.ModelAdmin):
    list_display = ("order", "user", "status", "created_at", "resolved_at")
    list_filter = ("status",)
    readonly_fields = tuple(field.name for field in CancellationRequest._meta.fields)


admin.site.register((Cart, CartItem, CouponRedemption, OrderEvent, WishlistItem))

