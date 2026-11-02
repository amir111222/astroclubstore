from django.urls import path

from . import views

app_name = "commerce"

urlpatterns = [
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/<str:slug>/", views.cart_add, name="cart_add"),
    path("cart/item/<int:item_id>/update/", views.cart_update, name="cart_update"),
    path("cart/item/<int:item_id>/decrease/", views.cart_decrease, name="cart_decrease"),
    path("cart/item/<int:item_id>/remove/", views.cart_remove, name="cart_remove"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/add/<str:slug>/", views.wishlist_add, name="wishlist_add"),
    path("wishlist/item/<int:item_id>/remove/", views.wishlist_remove, name="wishlist_remove"),
    path("wishlist/item/<int:item_id>/cart/", views.wishlist_to_cart, name="wishlist_to_cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("orders/", views.order_history, name="orders"),
    path("downloads/mine/", views.my_downloads, name="my_downloads"),
    path("downloads/order-item/<int:item_id>/<int:asset_id>/", views.paid_download, name="paid_download"),
    path("orders/<str:order_number>/", views.order_detail, name="order_detail"),
    path("orders/<str:order_number>/cancel/", views.request_cancellation, name="request_cancellation"),
]
