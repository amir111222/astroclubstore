from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import Coalesce
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .downloads import stream_asset
from .models import Category, DigitalAsset, Product
from .search import normalize_search


def product_list(request, category_slug=None):
    products = Product.objects.filter(status=Product.Status.PUBLISHED).select_related("category").prefetch_related("gallery", "variants")
    active_category = None
    if category_slug:
        active_category = get_object_or_404(Category, slug=category_slug, is_active=True)
        child_ids = list(active_category.children.filter(is_active=True).values_list("pk", flat=True))
        products = products.filter(Q(category=active_category) | Q(category_id__in=child_ids))
    query = normalize_search(request.GET.get("q", ""))[:100]
    if query:
        terms = query.split()
        for term in terms:
            products = products.filter(Q(name__icontains=term) | Q(sku__icontains=term) | Q(short_description__icontains=term) | Q(description__icontains=term) | Q(brand__icontains=term))
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    products = products.annotate(effective_price=Coalesce("sale_price_toman", "price_toman"))
    try:
        if min_price:
            products = products.filter(effective_price__gte=max(0, int(min_price)))
        if max_price:
            products = products.filter(effective_price__lte=max(0, int(max_price)))
    except (TypeError, ValueError):
        min_price = max_price = ""
    if request.GET.get("available") == "1":
        products = products.filter(Q(stock_quantity__gt=0) | Q(variants__stock_quantity__gt=0) | Q(product_type=Product.ProductType.DIGITAL, assets__is_active=True)).distinct()
    if request.GET.get("discounted") == "1":
        products = products.filter(Q(sale_price_toman__isnull=False) | Q(variants__sale_override_toman__isnull=False)).distinct()
    sort = request.GET.get("sort", "newest")
    if sort == "price_asc":
        products = products.order_by("effective_price", "pk")
    elif sort == "price_desc":
        products = products.order_by("-effective_price", "pk")
    elif sort == "popular":
        products = products.annotate(popularity=Count("order_items", filter=Q(order_items__order__payments__status="paid"), distinct=True)).order_by("-popularity", "-created_at")
    elif sort == "bestseller":
        products = products.order_by("-is_bestseller", "-created_at")
    else:
        sort = "newest"
        products = products.order_by("-created_at")
    page = Paginator(products, 12).get_page(request.GET.get("page"))
    categories = Category.objects.filter(is_active=True, parent__isnull=True)
    return render(request, "catalog/product_list.html", {
        "page_obj": page, "products": page.object_list, "categories": categories,
        "active_category": active_category, "query": query, "sort": sort,
        "min_price": min_price or "", "max_price": max_price or "",
        "available": request.GET.get("available") == "1", "discounted": request.GET.get("discounted") == "1",
    })


def category_list(request):
    categories = Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related("children")
    return render(request, "catalog/category_list.html", {"categories": categories})


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.filter(status=Product.Status.PUBLISHED).select_related("category").prefetch_related("gallery", "variants"),
        slug=slug,
    )
    related = Product.objects.filter(status=Product.Status.PUBLISHED, category=product.category).exclude(pk=product.pk)[:4] if product.category_id else Product.objects.none()
    return render(request, "catalog/product_detail.html", {"product": product, "related_products": related})


def free_downloads(request):
    products = Product.objects.filter(status=Product.Status.PUBLISHED, product_type=Product.ProductType.DIGITAL, is_free=True,
                                      assets__is_active=True).distinct().prefetch_related("assets").order_by("-created_at")
    page = Paginator(products, 12).get_page(request.GET.get("page"))
    return render(request, "catalog/free_downloads.html", {"page_obj": page, "products": page.object_list})


@login_required
def free_download(request, asset_id):
    asset = get_object_or_404(DigitalAsset.objects.select_related("product"), pk=asset_id, is_active=True,
                              product__is_free=True, product__status=Product.Status.PUBLISHED)
    return stream_asset(asset, "download.free", {"product": asset.product.sku, "user": request.user.pk})
