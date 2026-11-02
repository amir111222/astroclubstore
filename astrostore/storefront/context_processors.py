from pathlib import Path

from commerce.models import Cart
from django.conf import settings
from catalog.models import Category
from django.db.models import Prefetch
from .models import StoreSettings


def store_context(request):
    settings_obj = StoreSettings.objects.first()
    nav_categories = Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related(
        Prefetch("children", queryset=Category.objects.filter(is_active=True), to_attr="active_children")
    )
    cart = None
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
    else:
        token = request.session.get("guest_cart_token")
        if token:
            cart = Cart.objects.filter(guest_token=token).first()
    cart_count = sum(cart.items.values_list("quantity", flat=True)) if cart else 0
    cart_mini_items = (
        list(cart.items.select_related("product", "variant").order_by("-pk")[:5])
        if cart else []
    )
    can_manage = request.user.is_authenticated and request.user.is_staff and request.user.has_perm("storefront.view_store_dashboard")
    return {
        "store_settings": settings_obj,
        "nav_categories": nav_categories,
        "store_name": settings_obj.store_name if settings_obj else "نام فروشگاه",
        "cart_count": cart_count,
        "cart_mini_items": cart_mini_items,
        "show_manager_link": can_manage,
        "MEDIA_URL": settings.MEDIA_URL,
        "tailwind_built": (Path(settings.BASE_DIR) / "static" / "css" / "tailwind.generated.css").is_file(),
    }
