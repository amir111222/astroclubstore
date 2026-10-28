import tempfile
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from account.models import User
from catalog.models import DigitalAsset, Product
from commerce.models import Cart, Order, OrderItem
from commerce.services import StockError, add_to_cart, create_checkout_order
from commerce.pricing import build_quote, sign_quote

_TMP = tempfile.mkdtemp()


@override_settings(PRIVATE_MEDIA_ROOT=_TMP)
class DigitalProductTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="09121234567")
        self.other = User.objects.create_user(phone_number="09127654321")
        self.paid = self._product("paid", 5000, False)
        self.free = self._product("free", 1, True)

    def _product(self, slug, price, free):
        p = Product.objects.create(name=slug, slug=slug, sku=slug.upper(), price_toman=price, is_free=free,
                                   product_type=Product.ProductType.DIGITAL, status=Product.Status.PUBLISHED)
        asset = DigitalAsset(product=p, title="فایل", file=SimpleUploadedFile(f"{slug}.pdf", b"%PDF-1.4 test"))
        asset.save()
        return p

    def _order(self):
        cart = Cart.objects.create(user=self.user)
        add_to_cart(cart, self.paid)
        quote = build_quote(cart, self.user, None)
        self.assertEqual(quote.shipping_toman, 0)
        return cart, quote

    def test_free_product_cannot_enter_cart_and_digital_is_single(self):
        cart = Cart.objects.create(user=self.user)
        with self.assertRaises(StockError):
            add_to_cart(cart, self.free)
        add_to_cart(cart, self.paid)
        with self.assertRaises(StockError):
            add_to_cart(cart, self.paid)

    def test_digital_quote_has_no_shipping(self):
        cart, quote = self._order()
        self.assertEqual(quote.total_toman, 5000)

    def test_free_download_requires_login(self):
        asset = self.free.assets.first()
        url = reverse("catalog:free_download", kwargs={"asset_id": asset.pk})
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        asset.refresh_from_db()
        self.assertEqual(asset.download_count, 1)

    def test_paid_asset_is_not_free_downloadable(self):
        asset = self.paid.assets.first()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("catalog:free_download", kwargs={"asset_id": asset.pk})).status_code, 404)

    def test_paid_download_owner_status_and_limit(self):
        order = Order.objects.create(user=self.user, order_number="AS-DIG-1", status=Order.Status.DELIVERED, total_toman=5000,
                                     checkout_key=uuid.uuid4())
        item = OrderItem.objects.create(order=order, product=self.paid, product_name="paid", sku="PAID", quantity=1,
                                        regular_unit_toman=5000, sale_unit_toman=5000, line_total_toman=5000, is_digital=True)
        asset = self.paid.assets.first()
        url = reverse("commerce:paid_download", kwargs={"item_id": item.pk, "asset_id": asset.pk})
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.user)
        with override_settings(DIGITAL_DOWNLOAD_LIMIT=1):
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.get(url).status_code, 302)
        order.status = Order.Status.REFUNDED
        order.save()
        item.download_count = 0
        item.save()
        self.assertEqual(self.client.get(url).status_code, 302)