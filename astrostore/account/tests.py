from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import OTPForm, ProfileForm
from .models import Address, OTPChallenge, User
from .phone import normalize_phone
from .providers import SMSProviderError, send_verification_code
from .services import OTPRateLimited, request_otp, verify_otp


class PhoneAndFormTests(SimpleTestCase):
    def test_normalizes_iranian_digit_styles_and_prefixes(self):
        self.assertEqual(normalize_phone("۰۹۱۲ ۱۲۳ ۴۵۶۷"), "+989121234567")
        self.assertEqual(normalize_phone("+989121234567"), "+989121234567")
        self.assertEqual(normalize_phone("00989121234567"), "+989121234567")

    def test_rejects_non_iranian_or_incomplete_phone(self):
        with self.assertRaises(ValueError):
            normalize_phone("12345")

    def test_otp_form_normalizes_persian_digits(self):
        form = OTPForm({"code": "۱۲۳۴۵۶"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["code"], "123456")


class OTPServiceTests(TestCase):
    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=60)
    @patch("account.services.send_verification_code")
    def test_request_stores_only_digest_and_verifies_once(self, send_code):
        challenge = request_otp("09121234567", "127.0.0.1")
        delivered_code = send_code.call_args.args[1]
        challenge.refresh_from_db()
        self.assertTrue(challenge.delivered)
        self.assertNotEqual(challenge.code_digest, delivered_code)
        self.assertTrue(verify_otp(challenge.phone_number, delivered_code, "127.0.0.1"))
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.consumed_at)
        self.assertFalse(verify_otp(challenge.phone_number, delivered_code, "127.0.0.1"))

    @patch("account.services.send_verification_code")
    def test_expired_otp_is_rejected(self, send_code):
        challenge = request_otp("09121234567")
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.save(update_fields=("expires_at",))
        self.assertFalse(verify_otp(challenge.phone_number, send_code.call_args.args[1]))

    @patch("account.services.send_verification_code")
    def test_attempt_limit_prevents_later_correct_code(self, send_code):
        challenge = request_otp("09121234567")
        correct_code = send_code.call_args.args[1]
        wrong_code = "000001" if correct_code != "000001" else "000002"
        for _ in range(5):
            self.assertFalse(verify_otp(challenge.phone_number, wrong_code))
        self.assertFalse(verify_otp(challenge.phone_number, correct_code))

    @patch("account.services.send_verification_code")
    def test_resend_cooldown_is_enforced(self, send_code):
        request_otp("09121234567")
        with self.assertRaises(OTPRateLimited):
            request_otp("09121234567")
        self.assertEqual(send_code.call_count, 1)

    @override_settings(KAVENEGAR_API_KEY="", KAVENEGAR_OTP_TEMPLATE="")
    def test_sms_provider_never_simulates_delivery_without_credentials(self):
        with self.assertRaises(SMSProviderError):
            send_verification_code("+989121234567", "123456")


class AccountViewTests(TestCase):
    @patch("account.views.request_otp")
    @patch("account.views.verify_otp", return_value=True)
    def test_first_login_creates_account_persists_session_and_logout_revokes_it(self, verify_code, request_code):
        response = self.client.post(reverse("account:login"), {
            "phone_number": "۰۹۱۲۱۲۳۴۵۶۷",
            "remember_me": "on",
        })
        self.assertRedirects(response, reverse("account:verify"))
        self.assertTrue(request_code.called)
        response = self.client.post(reverse("account:verify"), {"code": "۱۲۳۴۵۶"})
        user = User.objects.get(phone_number="+989121234567")
        self.assertRedirects(response, reverse("storefront:home"))
        self.assertEqual(int(self.client.session.get_expiry_age()), 60 * 60 * 24 * 30)
        self.assertEqual(int(self.client.session.get("_auth_user_id")), user.pk)
        response = self.client.post(reverse("account:logout"))
        self.assertRedirects(response, reverse("storefront:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_verified_phone_cannot_be_changed_in_profile_form(self):
        self.assertNotIn("phone_number", ProfileForm().fields)

    def test_customer_cannot_edit_another_users_address(self):
        owner = User.objects.create_user(phone_number="09121234567")
        other = User.objects.create_user(phone_number="09121111111")
        address = Address.objects.create(
            user=owner, recipient_name="مشتری", recipient_phone="09121234567",
            province="تهران", city="تهران", postal_code="1234567890", address="خیابان نمونه",
        )
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("account:address_edit", args=(address.pk,))).status_code, 404)

    def test_deleting_default_address_promotes_another_address(self):
        user = User.objects.create_user(phone_number="09121234567")
        first = Address.objects.create(
            user=user, recipient_name="اول", recipient_phone="09121234567", province="تهران",
            city="تهران", postal_code="1234567890", address="نشانی اول", is_default=True,
        )
        second = Address.objects.create(
            user=user, recipient_name="دوم", recipient_phone="09121234567", province="تهران",
            city="تهران", postal_code="1234567890", address="نشانی دوم",
        )
        self.client.force_login(user)
        self.client.post(reverse("account:address_delete", args=(first.pk,)))
        second.refresh_from_db()
        self.assertTrue(second.is_default)
