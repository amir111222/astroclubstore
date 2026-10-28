from django.contrib.sitemaps import Sitemap

from catalog.models import Category, Product
from .models import ContentPage


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Product.objects.filter(status=Product.Status.PUBLISHED)

    def lastmod(self, item):
        return item.updated_at


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Category.objects.filter(is_active=True)


class ContentPageSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.4

    def items(self):
        return ContentPage.objects.filter(is_published=True)


class StaticSitemap(Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return ["storefront:home", "storefront:about", "storefront:contact", "storefront:faq", "catalog:products", "catalog:categories"]

    def location(self, item):
        from django.urls import reverse
        return reverse(item)
