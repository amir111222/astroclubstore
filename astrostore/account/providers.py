import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from .phone import local_phone


class SMSProviderError(Exception):
    """A safe-to-display SMS provider failure; never contains credentials or OTP values."""


def send_verification_code(phone_number, code):
    api_key = getattr(settings, "KAVENEGAR_API_KEY", "")
    template = getattr(settings, "KAVENEGAR_OTP_TEMPLATE", "")
    if not api_key and settings.DEBUG and getattr(settings, "OTP_CONSOLE_FALLBACK", True):
        # Development only: print the code instead of sending an SMS.
        print(f"[DEV OTP] {local_phone(phone_number)} -> {code}", flush=True)
        return True
    if not api_key or not template:
        raise SMSProviderError("سرویس پیامک پیکربندی نشده است.")
    endpoint = f"https://api.kavenegar.com/v1/{api_key}/verify/lookup.json"
    query = urlencode({"receptor": local_phone(phone_number), "token": code, "template": template})
    request = Request(f"{endpoint}?{query}", headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=getattr(settings, "KAVENEGAR_TIMEOUT", 8)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise SMSProviderError("ارتباط با سرویس پیامک برقرار نشد.") from exc
    result = payload.get("return", {}) if isinstance(payload, dict) else {}
    if result.get("status") != 200:
        raise SMSProviderError("سرویس پیامک درخواست را نپذیرفت.")
    return True
