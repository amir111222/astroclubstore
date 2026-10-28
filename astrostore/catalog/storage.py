import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    """Stores paid files outside MEDIA_ROOT; they have no public URL."""

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return str(Path(self.base_location).resolve())

    def url(self, name):
        raise ValueError("فایل‌های خصوصی آدرس عمومی ندارند.")


def digital_upload_to(instance, filename):
    suffix = Path(filename).suffix.lower()[:12]
    return f"digital/{uuid.uuid4().hex}{suffix}"
