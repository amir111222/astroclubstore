from django.contrib.sitemaps.views import sitemap
from django.urls import path

from . import manager_views, views
from .sitemaps import CategorySitemap, ContentPageSitemap, ProductSitemap, StaticSitemap

app_name = "storefront"

sitemaps = {"static": StaticSitemap, "products": ProductSitemap, "categories": CategorySitemap, "pages": ContentPageSitemap}

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("faq/", views.faq, name="faq"),
    path("pages/<str:slug>/", views.content_page, name="content_page"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("management/", manager_views.dashboard, name="manager_dashboard"),
    path("management/products/", manager_views.product_list, name="manager_products"),
    path("management/products/new/", manager_views.product_edit, name="manager_product_create"),
    path("management/products/<int:pk>/edit/", manager_views.product_edit, name="manager_product_edit"),
    path("management/products/<int:pk>/duplicate/", manager_views.product_duplicate, name="manager_product_duplicate"),
    path("management/digital/", manager_views.digital_list, name="manager_digital"),
    path("management/digital/new/", manager_views.digital_edit, name="manager_digital_create"),
    path("management/digital/<int:pk>/edit/", manager_views.digital_edit, name="manager_digital_edit"),
    path("management/categories/", manager_views.category_list, name="manager_categories"),
    path("management/categories/new/", manager_views.category_edit, name="manager_category_create"),
    path("management/categories/<int:pk>/edit/", manager_views.category_edit, name="manager_category_edit"),
    path("management/categories/<int:pk>/deactivate/", manager_views.category_deactivate, name="manager_category_deactivate"),
    path("management/inventory/", manager_views.inventory, name="manager_inventory"),
    path("management/orders/", manager_views.order_list, name="manager_orders"),
    path("management/orders/export.csv", manager_views.order_export, name="manager_order_export"),
    path("management/orders/<str:order_number>/", manager_views.order_detail, name="manager_order_detail"),
    path("management/orders/<str:order_number>/status/", manager_views.order_status, name="manager_order_status"),
    path("management/orders/<str:order_number>/cancellation/", manager_views.cancellation_resolution, name="manager_cancellation_resolution"),
    path("management/orders/<str:order_number>/refund/", manager_views.refund_request, name="manager_refund_request"),
    path("management/refunds/<int:pk>/reconcile/", manager_views.refund_reconcile, name="manager_refund_reconcile"),
    path("management/settings/", manager_views.store_settings, name="manager_settings"),
    path("management/shipping/", manager_views.shipping_rates, name="manager_shipping"),
    path("management/shipping/new/", manager_views.shipping_rate_edit, name="manager_shipping_create"),
    path("management/shipping/<int:pk>/edit/", manager_views.shipping_rate_edit, name="manager_shipping_edit"),
    path("management/banners/", manager_views.banners, name="manager_banners"),
    path("management/banners/new/", manager_views.banner_edit, name="manager_banner_create"),
    path("management/banners/<int:pk>/edit/", manager_views.banner_edit, name="manager_banner_edit"),
    path("management/sections/", manager_views.home_sections, name="manager_sections"),
    path("management/sections/new/", manager_views.home_section_edit, name="manager_section_create"),
    path("management/sections/<int:pk>/edit/", manager_views.home_section_edit, name="manager_section_edit"),
    path("management/pages/", manager_views.content_pages, name="manager_pages"),
    path("management/pages/new/", manager_views.content_page_edit, name="manager_page_create"),
    path("management/pages/<int:pk>/edit/", manager_views.content_page_edit, name="manager_page_edit"),
    path("management/faqs/", manager_views.faqs, name="manager_faqs"),
    path("management/faqs/new/", manager_views.faq_edit, name="manager_faq_create"),
    path("management/faqs/<int:pk>/edit/", manager_views.faq_edit, name="manager_faq_edit"),
    path("management/coupons/", manager_views.coupons, name="manager_coupons"),
    path("management/coupons/new/", manager_views.coupon_edit, name="manager_coupon_create"),
    path("management/coupons/<int:pk>/edit/", manager_views.coupon_edit, name="manager_coupon_edit"),
    path("management/audit/", manager_views.audit_log, name="manager_audit"),
]
