import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import Address, User
from catalog.models import InventoryMovement, Product
from storefront.models import StoreSettings

from commerce.models import Cart, CartItem, Coupon, Order
from commerce.pricing import QuoteChanged, build_quote, sign_quote
from commerce.services import (
    StockError, add_to_cart, cancel_unpaid_order, create_checkout_order, update_cart_item,
)


class CommerceWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="09121234567")
        self.address = Address.objects.create(
            user=self.user, recipient_name="آزمون", recipient_phone="09121234567",
            province="تهران", city="تهران", postal_code="1234567890", address="خیابان نمونه",
            is_default=True,
        )
        self.product = Product.objects.create(
            name="محصول نمونه", slug="sample", sku="SAMPLE-1", price_toman=1000,
            sale_price_toman=800, stock_quantity=5, status=Product.Status.PUBLISHED,
        )
        self.cart = Cart.objects.create(user=self.user)
        self.item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        settings_obj = StoreSettings.get_solo()
        settings_obj.default_shipping_toman = 100
        settings_obj.free_shipping_threshold_toman = None
        settings_obj.tax_enabled = False
        settings_obj.save()

    def test_pricing_is_server_calculated_and_includes_sale_and_shipping(self):
        quote = build_quote(self.cart, self.user, self.address)
        self.assertEqual(quote.subtotal_toman, 2000)
        self.assertEqual(quote.item_discount_toman, 400)
        self.assertEqual(quote.shipping_toman, 100)
        self.assertEqual(quote.total_toman, 1700)

    def test_tax_and_coupon_are_applied_from_store_configuration(self):
        coupon = Coupon.objects.create(
            code="SAVE10", discount_type=Coupon.DiscountType.PERCENT, value=10,
            per_customer_limit=1, is_active=True,
        )
        settings_obj = StoreSettings.get_solo()
        settings_obj.tax_enabled = True
        settings_obj.tax_rate_percent = 10
        settings_obj.save()
        quote = build_quote(self.cart, self.user, self.address, coupon.code)
        self.assertEqual(quote.coupon_discount_toman, 160)
        self.assertEqual(quote.tax_toman, 144)
        self.assertEqual(quote.total_toman, 1684)

    def test_checkout_reserves_stock_and_records_immutable_price_snapshot(self):
        quote = build_quote(self.cart, self.user, self.address)
        token = sign_quote(self.user, self.cart, self.address, "", quote)
        order, created = create_checkout_order(
            cart=self.cart, user=self.user, address=self.address, coupon_code="",
            checkout_key=uuid.uuid4(), quote_token=token,
        )
        self.assertTrue(created)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        row = order.items.get()
        self.assertEqual(row.product_name, "محصول نمونه")
        self.assertEqual(row.regular_unit_toman, 1000)
        self.assertEqual(row.sale_unit_toman, 800)
        self.assertEqual(row.quantity, 2)
        self.assertEqual(InventoryMovement.objects.filter(reference=order.order_number).count(), 1)

    def test_stale_quote_is_rejected(self):
        quote = build_quote(self.cart, self.user, self.address)
        token = sign_quote(self.user, self.cart, self.address, "", quote)
        self.product.price_toman = 1200
        self.product.save(update_fields=("price_toman",))
        with self.assertRaises(QuoteChanged):
            create_checkout_order(
                cart=self.cart, user=self.user, address=self.address, coupon_code="",
                checkout_key=uuid.uuid4(), quote_token=token,
            )

    def test_unpaid_cancel_releases_inventory_once(self):
        quote = build_quote(self.cart, self.user, self.address)
        token = sign_quote(self.user, self.cart, self.address, "", quote)
        order, _ = create_checkout_order(
            cart=self.cart, user=self.user, address=self.address, coupon_code="",
            checkout_key=uuid.uuid4(), quote_token=token,
        )
        self.assertTrue(cancel_unpaid_order(order, "آزمون"))
        self.assertFalse(cancel_unpaid_order(order, "تکرار"))
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)
        self.assertFalse(order.stock_reserved)
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_cart_rejects_quantity_over_stock_and_scopes_item_updates(self):
        with self.assertRaises(StockError):
            add_to_cart(self.cart, self.product, quantity=10)
        stranger = User.objects.create_user(phone_number="09121111111")
        other_cart = Cart.objects.create(user=stranger)
        with self.assertRaises(CartItem.DoesNotExist):
            update_cart_item(other_cart, self.item.pk, 1)

    def test_customer_cannot_view_another_customers_order(self):
        other = User.objects.create_user(phone_number="09121111111")
        order = Order.objects.create(
            order_number="AS-PRIVATE-1", user=self.user, total_toman=1000,
            address_snapshot={"city": "تهران"},
        )
        self.client.force_login(other)
        response = self.client.get(reverse("commerce:order_detail", args=(order.order_number,)))
        self.assertEqual(response.status_code, 404)
