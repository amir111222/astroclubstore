from django.db.models import F
from django.http import FileResponse, Http404

from storefront.models import AuditLog

from .models import DigitalAsset


def stream_asset(asset, action, extra=None):
    try:
        handle = asset.file.open("rb")
    except (FileNotFoundError, ValueError, OSError):
        raise Http404("فایل در دسترس نیست.")
    DigitalAsset.objects.filter(pk=asset.pk).update(download_count=F("download_count") + 1)
    AuditLog.objects.create(action=action, object_type="DigitalAsset", object_id=str(asset.pk), changes=extra or {})
    response = FileResponse(handle, as_attachment=True, filename=asset.original_name or "download")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
