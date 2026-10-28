from django.core.management.base import BaseCommand

from commerce.services import expire_reservations


class Command(BaseCommand):
    help = "Release inventory and coupon reservations whose payment window has expired."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options):
        limit = max(1, min(options["limit"], 5000))
        released = expire_reservations(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Released {released} expired order reservation(s)."))

