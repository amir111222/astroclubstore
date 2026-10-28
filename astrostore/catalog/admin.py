from django.contrib import admin

from .models import Category, DigitalAsset, InventoryMovement, Product, ProductImage, ProductVariant


class VariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    readonly_fields = ("stock_quantity",)


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class AssetInline(admin.TabularInline):
    model = DigitalAsset
    extra = 0
    readonly_fields = ("original_name", "size_bytes", "checksum_sha256", "download_count")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "price_toman", "status", "is_featured")
    list_filter = ("status", "category", "is_featured", "is_new", "is_bestseller")
    search_fields = ("name", "sku", "brand")
    inlines = (VariantInline, ImageInline, AssetInline)
    readonly_fields = ("created_at", "updated_at", "stock_quantity")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "position", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "variant", "delta", "reason", "actor", "created_at")
    list_filter = ("reason",)
    search_fields = ("product__name", "product__sku", "reference")
    readonly_fields = tuple(field.name for field in InventoryMovement._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
