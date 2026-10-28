from datetime import timedelta
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from account.models import User
from catalog.models import Product
from commerce.models import Order, OrderItem
from commerce.services import expire_reservations
from payments.gateways import GatewayError
from payments.models import PaymentTransaction
from payments.services import create_transaction, handle_callback, initiate_payment


class PaymentWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="09121234567")
        self.product = Product.objects.create(
            name="پرداخت نمونه", slug="pay-sample", sku="PAY-1", price_toman=500,
            stock_quantity=4, status=Product.Status.PUBLISHED,
        )
        self.order = Order.objects.create(
            order_number="AS-PAY-1", user=self.user, total_toman=500,
            status=Order.Status.AWAITING_PAYMENT, stock_reserved=True,
            reservation_expires_at=timezone.now() - timedelta(seconds=1),
            address_snapshot={"city": "تهران"},
        )
        OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            sku=self.product.sku, quantity=1, regular_unit_toman=500,
            sale_unit_toman=500, line_total_toman=500,
        )
        self.payment = PaymentTransaction.objects.create(
            order=self.order, amount_toman=500, amount_rial=5000,
            authority="A0000000001", status=PaymentTransaction.Status.AWAITING_VERIFICATION,
        )

    @override_settings(ZARINPAL_TOMAN_TO_RIAL=10)
    def test_transaction_converts_toman_to_configured_rial(self):
        second = Order.objects.create(order_number="AS-PAY-2", user=self.user, total_toman=750)
        tx = create_transaction(second)
        self.assertEqual(tx.amount_toman, 750)
        self.assertEqual(tx.amount_rial, 7500)

    @patch("payments.services.verify_payment", return_value={"code": "100", "ref_id": "900123"})
    def test_successful_callback_verifies_payment_and_advances_order_once(self, verify):
        order, result = handle_callback(self.payment.authority, "OK")
        self.assertEqual(result, "paid")
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.payment.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentTransaction.Status.PAID)
        self.assertEqual(self.payment.reference_id, "900123")
        self.assertEqual(self.product.stock_quantity, 4)
        _, duplicate = handle_callback(self.payment.authority, "OK")
        self.assertEqual(duplicate, "paid")
        verify.assert_called_once()

    def test_unknown_and_non_success_callbacks_do_not_claim_payment(self):
        self.assertEqual(handle_callback("UNKNOWN", "OK"), (None, "unknown"))
        order, result = handle_callback(self.payment.authority, "NOK")
        self.assertEqual(result, "cancelled")
        self.payment.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentTransaction.Status.CANCELLED)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock_quantity, 5)

    @patch("payments.services.verify_payment", return_value={"code": "100", "ref_id": "900123"})
    def test_amount_mismatch_enters_review_and_keeps_stock_reserved(self, verify):
        self.order.total_toman = 501
        self.order.save(update_fields=("total_toman",))
        _, result = handle_callback(self.payment.authority, "OK")
        self.assertEqual(result, "review")
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentTransaction.Status.REVIEW)
        self.assertEqual(self.order.status, Order.Status.PAYMENT_REVIEW)
        self.assertTrue(self.order.stock_reserved)
        self.assertEqual(expire_reservations(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 4)

    @patch("payments.services.request_payment", side_effect=GatewayError("provider unavailable"))
    def test_initiation_failure_cancels_order_and_releases_stock(self, request_payment):
        self.payment.status = PaymentTransaction.Status.PENDING
        self.payment.authority = None
        self.payment.save(update_fields=("status", "authority"))
        factory = RequestFactory()
        request = factory.get("/", HTTP_HOST="testserver")
        with self.assertRaises(GatewayError):
            initiate_payment(self.payment, request)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentTransaction.Status.INITIATION_FAILED)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock_quantity, 5)
        request_payment.assert_called_once()

    @override_settings(ZARINPAL_MERCHANT_ID="merchant-test")
    @patch("payments.gateways._post", return_value={"data": {"code": 100, "authority": "A-test"}})
    def test_zarinpal_request_payload_uses_v4_contract(self, post):
        from payments.gateways import request_payment
        authority = request_payment(amount_rial=2500, description="سفارش آزمون", callback_url="https://example.test/callback/")
        self.assertEqual(authority, "A-test")
        payload = post.call_args.args[1]
        self.assertEqual(payload["amount"], 2500)
        self.assertEqual(payload["merchant_id"], "merchant-test")
