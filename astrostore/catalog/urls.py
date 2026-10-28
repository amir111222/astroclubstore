from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("products/", views.product_list, name="products"),
    path("downloads/", views.free_downloads, name="free_downloads"),
    path("downloads/file/<int:asset_id>/", views.free_download, name="free_download"),
    path("categories/", views.category_list, name="categories"),
    path("categories/<str:category_slug>/", views.product_list, name="category"),
    path("products/<str:slug>/", views.product_detail, name="product"),
    path("search/", views.product_list, name="search"),
]
