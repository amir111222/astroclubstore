from django.test import TestCase
from django.urls import reverse

from account.models import User
from commerce.models import CancellationRequest, Order
from payments.models import PaymentTransaction, RefundRecord


class ManagerPermissionTests(TestCase):
    def test_staff_without_explicit_permission_cannot_manage_products(self):
        staff = User.objects.create_user(phone_number="09121234567", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("storefront:manager_products")).status_code, 403)

    def test_superuser_can_render_manager_dashboard_and_content_tools(self):
        owner = User.objects.create_superuser(phone_number="09121234567", password="safe-test-password")
        self.client.force_login(owner)
        self.assertEqual(self.client.get(reverse("storefront:manager_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("storefront:manager_banners")).status_code, 200)
        self.assertEqual(self.client.get(reverse("storefront:manager_product_create")).status_code, 200)


class ManagerRefundWorkflowTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_superuser(phone_number="09121234567", password="safe-test-password")
        self.customer = User.objects.create_user(phone_number="09129876543")
        self.client.force_login(self.manager)
        self.order = Order.objects.create(
            order_number="AS-REFUND-1", user=self.customer, total_toman=1000,
            status=Order.Status.CANCEL_REQUESTED, stock_reserved=True,
        )
        self.payment = PaymentTransaction.objects.create(
            order=self.order, amount_toman=1000, amount_rial=10000,
            status=PaymentTransaction.Status.PAID, reference_id="PAY-REF-1",
        )
        self.cancellation = CancellationRequest.objects.create(
            order=self.order, user=self.customer, previous_order_status=Order.Status.PROCESSING,
        )

    def test_cancellation_refund_only_reserves_remaining_amount_and_is_idempotent(self):
        RefundRecord.objects.create(
            payment=self.payment, amount_toman=300, reason="partial complete",
            status=RefundRecord.Status.CONFIRMED, requested_by=self.manager,
        )
        RefundRecord.objects.create(
            payment=self.payment, amount_toman=200, reason="pending",
            status=RefundRecord.Status.SUBMITTED, requested_by=self.manager,
        )
        url = reverse("storefront:manager_cancellation_resolution", args=(self.order.order_number,))

        self.client.post(url, {"action": "approve"})
        self.cancellation.refresh_from_db()
        self.assertEqual(self.cancellation.status, CancellationRequest.Status.APPROVED)
        refunds = list(self.payment.refunds.order_by("amount_toman").values_list("amount_toman", flat=True))
        self.assertEqual(refunds, [200, 300, 500])

        self.client.post(url, {"action": "approve"})
        self.assertEqual(self.payment.refunds.count(), 3)

    def test_refund_request_accepts_only_confirmed_review_receipts(self):
        self.payment.status = PaymentTransaction.Status.REVIEW
        self.payment.provider_code = "100"
        self.payment.reference_id = "CONFIRMED-REF"
        self.payment.save(update_fields=("status", "provider_code", "reference_id"))
        url = reverse("storefront:manager_refund_request", args=(self.order.order_number,))

        self.client.post(url, {"amount_toman": 300, "reason": "customer request"})
        self.assertEqual(self.payment.refunds.count(), 1)

        self.payment.provider_code = "0"
        self.payment.save(update_fields=("provider_code",))
        self.client.post(url, {"amount_toman": 300, "reason": "unverified receipt"})
        self.assertEqual(self.payment.refunds.count(), 1)

    def test_order_detail_shows_refund_form_for_verified_review_payment(self):
        self.payment.status = PaymentTransaction.Status.REVIEW
        self.payment.provider_code = "100"
        self.payment.reference_id = "CONFIRMED-REF"
        self.payment.save(update_fields=("status", "provider_code", "reference_id"))

        response = self.client.get(reverse("storefront:manager_order_detail", args=(self.order.order_number,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="amount_toman"')

    def test_refund_reconcile_rejects_terminal_and_overpayment_transitions(self):
        failed = RefundRecord.objects.create(
            payment=self.payment, amount_toman=100, reason="failed",
            status=RefundRecord.Status.FAILED, requested_by=self.manager,
        )
        url = reverse("storefront:manager_refund_reconcile", args=(failed.pk,))
        self.client.post(url, {"status": RefundRecord.Status.CONFIRMED, "external_reference": "RF-1"})
        failed.refresh_from_db()
        self.assertEqual(failed.status, RefundRecord.Status.FAILED)

        RefundRecord.objects.create(
            payment=self.payment, amount_toman=600, reason="already returned",
            status=RefundRecord.Status.CONFIRMED, requested_by=self.manager,
        )
        pending = RefundRecord.objects.create(
            payment=self.payment, amount_toman=500, reason="excess",
            requested_by=self.manager,
        )
        url = reverse("storefront:manager_refund_reconcile", args=(pending.pk,))
        self.client.post(url, {"status": RefundRecord.Status.CONFIRMED, "external_reference": "RF-2"})
        pending.refresh_from_db()
        self.assertEqual(pending.status, RefundRecord.Status.REQUESTED)
