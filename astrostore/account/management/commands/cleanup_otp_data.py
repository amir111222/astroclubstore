from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from account.models import OTPChallenge, OTPThrottle


class Command(BaseCommand):
    help = "Delete expired OTP challenges and stale rate-limit buckets."

    def handle(self, *args, **options):
        now = timezone.now()
        challenges, _ = OTPChallenge.objects.filter(
            expires_at__lt=now - timedelta(days=7),
        ).delete()
        throttles, _ = OTPThrottle.objects.filter(
            window_started_at__lt=now - timedelta(days=2),
        ).delete()
        self.stdout.write(self.style.SUCCESS(
            f"Deleted {challenges} OTP challenge row(s) and {throttles} throttle row(s)."
        ))

