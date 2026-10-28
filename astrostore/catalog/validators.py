from django.core.exceptions import ValidationError
from django.conf import settings

DIGITAL_EXTENSIONS = {"pdf", "zip", "epub", "mp3", "mp4", "txt", "docx", "xlsx", "pptx", "rar", "7z"}


def validate_digital_upload(file):
    name = (getattr(file, "name", "") or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in DIGITAL_EXTENSIONS:
        raise ValidationError("فرمت فایل مجاز نیست. فرمت‌های مجاز: " + "، ".join(sorted(DIGITAL_EXTENSIONS)))
    limit = int(getattr(settings, "DIGITAL_MAX_UPLOAD_MB", 200)) * 1024 * 1024
    if file.size > limit:
        raise ValidationError("حجم فایل از سقف مجاز بیشتر است.")


def validate_image_upload(file):
    if file.size > 5 * 1024 * 1024:
        raise ValidationError("حجم تصویر نباید بیشتر از ۵ مگابایت باشد.")
    position = file.tell() if hasattr(file, "tell") else 0
    header = file.read(16)
    if hasattr(file, "seek"):
        file.seek(position)
    valid = (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith((b"GIF87a", b"GIF89a"))
        or (header[:4] == b"RIFF" and header[8:12] == b"WEBP")
    )
    if not valid:
        raise ValidationError("فقط تصویرهای JPEG، PNG، GIF یا WebP پذیرفته می‌شوند.")
