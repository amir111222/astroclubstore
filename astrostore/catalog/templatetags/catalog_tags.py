import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def fa_num(value):
    digits = str(value if value is not None else "").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return digits


@register.filter
def toman(value):
    try:
        amount = f"{int(value):,}"
    except (TypeError, ValueError):
        amount = "۰"
    return fa_num(amount)


@register.filter
def product_json_ld(product):
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "description": product.short_description or product.description[:300],
        "sku": product.sku,
        "offers": {
            "@type": "Offer",
            "priceCurrency": "IRR",
            "price": str(product.available_price_toman * 10),
            "availability": "https://schema.org/InStock" if product.is_available else "https://schema.org/OutOfStock",
        },
    }
    encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(encoded)
