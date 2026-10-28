from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from commerce.models import CartItem
from catalog.forms import ProductForm
from catalog.models import Product
from catalog.validators import validate_image_upload


class CatalogTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="کتاب نمونه", slug="کتاب-نمونه", sku="BOOK-1",
            price_toman=150000, stock_quantity=4, status=Product.Status.PUBLISHED,
        )

    def test_persian_slug_product_page_and_cart_routes_work(self):
        response = self.client.get(reverse("catalog:product", kwargs={"slug": self.product.slug}))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("commerce:cart_add", kwargs={"slug": self.product.slug}), {"quantity": "1"})
        self.assertRedirects(response, reverse("commerce:cart"))
        self.assertEqual(CartItem.objects.count(), 1)

    def test_product_form_does_not_allow_inventory_bypass(self):
        self.assertNotIn("stock_quantity", ProductForm().fields)

    def test_rejects_disguised_non_image_upload(self):
        upload = SimpleUploadedFile("fake.png", b"not-an-image", content_type="image/png")
        with self.assertRaises(ValidationError):
            validate_image_upload(upload)

    def test_search_listing_renders_empty_state(self):
        self.product.status = Product.Status.DRAFT
        self.product.save(update_fields=("status",))
        response = self.client.get(reverse("catalog:products"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "محصولی پیدا نشد")
