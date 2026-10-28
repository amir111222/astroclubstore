import unicodedata


_MAP = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "ٱ": "ا"})


def normalize_search(value):
    text = unicodedata.normalize("NFKC", str(value or "")).translate(_MAP)
    return " ".join(text.replace("\u200c", " ").split())
