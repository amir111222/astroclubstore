from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from commerce.models import Order

from .services import handle_callback


@require_GET
def callback(request):
    authority = request.GET.get("Authority", "")[:100]
    gateway_status = request.GET.get("Status", "")[:20]
    order, result = handle_callback(authority, gateway_status) if authority else (None, "unknown")
    if order is None:
        return render(request, "payments/result.html", {"result": "unknown", "order": None})
    if request.user.is_authenticated and request.user.pk == order.user_id:
        return redirect("payments:result", order_number=order.order_number)
    return render(request, "payments/result.html", {"result": result, "order": None, "requires_login": True})


@login_required
@require_GET
def result(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related("payments"), order_number=order_number, user=request.user)
    payment = order.payments.order_by("-created_at").first()
    if payment and payment.status == payment.Status.PAID:
        state = "paid" if order.status != Order.Status.PAYMENT_REVIEW else "review"
    elif payment and payment.status in (payment.Status.CANCELLED, payment.Status.FAILED, payment.Status.INITIATION_FAILED, payment.Status.EXPIRED):
        state = "failed"
    else:
        state = "pending"
    return render(request, "payments/result.html", {"result": state, "order": order, "payment": payment})
