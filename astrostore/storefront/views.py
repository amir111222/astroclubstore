from django.conf import settings as django_settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product
from commerce.models import Order

from .models import ContentPage, FAQ, HeroBanner, HomeSection, StoreSettings


def home(request):
    store_settings = StoreSettings.get_solo()
    sections = []
    for section in HomeSection.objects.filter(is_visible=True).prefetch_related("products", "category").order_by("position"):
        if section.products.exists():
            products = section.products.filter(status=Product.Status.PUBLISHED)
        elif section.kind == HomeSection.Kind.FEATURED:
            products = Product.objects.filter(status=Product.Status.PUBLISHED, is_featured=True)
        elif section.kind == HomeSection.Kind.NEW:
            products = Product.objects.filter(status=Product.Status.PUBLISHED, is_new=True)
        elif section.kind == HomeSection.Kind.BESTSELLER:
            products = Product.objects.filter(status=Product.Status.PUBLISHED, is_bestseller=True)
        elif section.kind == HomeSection.Kind.DISCOUNT:
            products = Product.objects.filter(status=Product.Status.PUBLISHED, sale_price_toman__isnull=False)
        elif section.kind == HomeSection.Kind.CATEGORY and section.category:
            products = Product.objects.filter(status=Product.Status.PUBLISHED, category=section.category)
        else:
            products = Product.objects.none()
        section.product_list = products.select_related("category").prefetch_related("gallery", "variants")[:8]
        sections.append(section)
    if not sections:
        for title, kind, filters in (
            ("محصولات ویژه", "featured", {"is_featured": True}),
            ("تازه‌واردها", "new", {"is_new": True}),
            ("پیشنهادها", "discount", {"sale_price_toman__isnull": False}),
        ):
            products = Product.objects.filter(status=Product.Status.PUBLISHED, **filters).select_related("category").prefetch_related("gallery", "variants")[:8]
            if products:
                section = HomeSection(title=title, kind=kind)
                section.product_list = products
                sections.append(section)
    return render(request, "storefront/home.html", {
        "store_settings": store_settings,
        "banners": HeroBanner.active()[:5],
        "categories": Category.objects.filter(is_active=True, parent__isnull=True)[:8],
        "sections": sections,
        "page_title": store_settings.store_name,
        "meta_description": "محصولات فروشگاه را ببینید و سفارش خود را ثبت کنید.",
    })


def content_page(request, slug):
    page = ContentPage.objects.filter(slug=slug, is_published=True).first()
    if page:
        return render(request, "storefront/content_page.html", {"page": page, "page_title": page.title, "meta_description": page.meta_description})
    built_in = {
        "shipping": "ارسال و تحویل",
        "returns": "بازگشت کالا",
        "privacy": "حریم خصوصی",
        "terms": "شرایط استفاده",
    }
    if slug in built_in:
        return render(request, "storefront/content_page.html", {
            "page": None,
            "page_title": built_in[slug],
            "placeholder_title": built_in[slug],
            "placeholder_body": "جزئیات این صفحه هنوز توسط مدیر فروشگاه تنظیم نشده است.",
        })
    return render(request, "404.html", status=404)


def about(request):
    page = ContentPage.objects.filter(slug="about", is_published=True).first()
    return render(request, "storefront/information_page.html", {"page": page, "title": page.title if page else "دربارهٔ فروشگاه", "store_settings": StoreSettings.get_solo()})


def contact(request):
    page = ContentPage.objects.filter(slug="contact", is_published=True).first()
    return render(request, "storefront/contact.html", {"page": page, "store_settings": StoreSettings.get_solo(), "page_title": "تماس با ما"})


def faq(request):
    questions = FAQ.objects.filter(is_published=True)
    return render(request, "storefront/faq.html", {"questions": questions, "page_title": "پرسش‌های پرتکرار"})


def robots_txt(request):
    origin = request.build_absolute_uri("/").rstrip("/")
    body = "User-agent: *\nAllow: /\nDisallow: /management/\nDisallow: /account/\nDisallow: /cart/\nDisallow: /checkout/\nDisallow: /orders/\nSitemap: " + origin + reverse("storefront:sitemap") + "\n"
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)
