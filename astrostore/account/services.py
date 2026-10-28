import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import OTPChallenge, OTPThrottle
from .phone import normalize_phone
from .providers import SMSProviderError, send_verification_code


class OTPError(Exception):
    pass


class OTPRateLimited(OTPError):
    pass


def _key_digest(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def _consume_bucket(key, limit, window_seconds):
    now = timezone.now()
    digest = _key_digest(key)
    bucket, _ = OTPThrottle.objects.get_or_create(key_digest=digest, defaults={"window_started_at": now, "count": 0})
    bucket = OTPThrottle.objects.select_for_update().get(pk=bucket.pk)
    if now - bucket.window_started_at >= timedelta(seconds=window_seconds):
        bucket.window_started_at, bucket.count = now, 0
    if bucket.count >= limit:
        raise OTPRateLimited
    bucket.count += 1
    bucket.save(update_fields=("window_started_at", "count"))


def _code_digest(challenge_id, code):
    raw = f"{challenge_id}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()


def request_otp(phone_number, ip_address=None):
    phone = normalize_phone(phone_number)
    now = timezone.now()
    code = f"{secrets.randbelow(1_000_000):06d}"
    with transaction.atomic():
        latest = OTPChallenge.objects.select_for_update().filter(phone_number=phone).first()
        cooldown = int(getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60))
        if latest and now - latest.created_at < timedelta(seconds=cooldown):
            raise OTPRateLimited
        _consume_bucket(f"send:phone:{phone}", int(getattr(settings, "OTP_PHONE_LIMIT_PER_HOUR", 5)), 3600)
        if ip_address:
            _consume_bucket(f"send:ip:{ip_address}", int(getattr(settings, "OTP_IP_LIMIT_PER_HOUR", 20)), 3600)
        challenge = OTPChallenge.objects.create(
            phone_number=phone,
            code_digest="",
            requested_ip=ip_address,
            expires_at=now + timedelta(seconds=int(getattr(settings, "OTP_EXPIRY_SECONDS", 300))),
        )
        challenge.code_digest = _code_digest(challenge.pk, code)
        challenge.save(update_fields=("code_digest",))
    try:
        send_verification_code(phone, code)
    except SMSProviderError:
        raise
    OTPChallenge.objects.filter(pk=challenge.pk).update(delivered=True)
    return challenge


def verify_otp(phone_number, code, ip_address=None):
    phone = normalize_phone(phone_number)
    with transaction.atomic():
        challenge = OTPChallenge.objects.select_for_update().filter(phone_number=phone, consumed_at__isnull=True).first()
        if challenge is None or challenge.attempts >= int(getattr(settings, "OTP_MAX_ATTEMPTS", 5)):
            return False
        _consume_bucket(f"verify:phone:{phone}", int(getattr(settings, "OTP_VERIFY_PHONE_LIMIT_PER_HOUR", 15)), 3600)
        if ip_address:
            _consume_bucket(f"verify:ip:{ip_address}", int(getattr(settings, "OTP_VERIFY_IP_LIMIT_PER_HOUR", 40)), 3600)
        challenge.attempts += 1
        challenge.save(update_fields=("attempts",))
        if timezone.now() >= challenge.expires_at or not challenge.delivered:
            return False
        if not hmac.compare_digest(challenge.code_digest, _code_digest(challenge.pk, str(code))):
            return False
        challenge.consumed_at = timezone.now()
        challenge.code_digest = ""
        challenge.save(update_fields=("consumed_at", "code_digest"))
        return True
