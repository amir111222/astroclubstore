import re


_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(value):
    return str(value or "").translate(_DIGIT_MAP)


def normalize_phone(value):
    raw = normalize_digits(value).strip()
    digits = re.sub(r"[\s().-]", "", raw)
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("+98"):
        digits = digits[3:]
    elif digits.startswith("98"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"9\d{9}", digits):
        raise ValueError("شمارهٔ تلفن همراه ایران معتبر نیست.")
    return "+98" + digits


def local_phone(value):
    normalized = normalize_phone(value)
    return "0" + normalized[3:]
