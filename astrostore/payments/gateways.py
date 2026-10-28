import json
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.conf import settings


class GatewayError(Exception):
    """Provider failures with no secret or payment credentials in the message."""


def _post(path, payload):
    base = getattr(settings, "ZARINPAL_API_BASE_URL", "https://api.zarinpal.com").rstrip("/") + "/"
    request = Request(
        urljoin(base, path.lstrip("/")),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=int(getattr(settings, "ZARINPAL_TIMEOUT", 10))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise GatewayError("ارتباط با درگاه پرداخت برقرار نشد.") from exc
    if not isinstance(data, dict):
        raise GatewayError("پاسخ درگاه پرداخت معتبر نیست.")
    return data


def request_payment(*, amount_rial, description, callback_url, mobile=None):
    merchant_id = getattr(settings, "ZARINPAL_MERCHANT_ID", "")
    if not merchant_id:
        raise GatewayError("درگاه پرداخت پیکربندی نشده است.")
    metadata = {"mobile": mobile} if mobile else {}
    payload = {
        "merchant_id": merchant_id,
        "amount": amount_rial,
        "description": description[:255],
        "callback_url": callback_url,
        "metadata": metadata,
    }
    result = _post("pg/v4/payment/request.json", payload)
    data = result.get("data", {})
    if int(data.get("code", 0)) != 100 or not data.get("authority"):
        raise GatewayError("درگاه پرداخت نتوانست درخواست را ثبت کند.")
    return str(data["authority"])


def verify_payment(*, amount_rial, authority):
    merchant_id = getattr(settings, "ZARINPAL_MERCHANT_ID", "")
    if not merchant_id:
        raise GatewayError("درگاه پرداخت پیکربندی نشده است.")
    result = _post("pg/v4/payment/verify.json", {
        "merchant_id": merchant_id,
        "amount": amount_rial,
        "authority": authority,
    })
    data = result.get("data", {})
    return {"code": str(data.get("code", "")), "ref_id": str(data.get("ref_id", ""))}
