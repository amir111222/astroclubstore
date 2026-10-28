from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import AccountDeletionForm, AddressForm, OTPForm, PhoneForm, ProfileForm
from .models import AccountDeletionRequest, Address, User
from .providers import SMSProviderError
from .services import OTPRateLimited, request_otp, verify_otp


def _ip(request):
    return request.META.get("REMOTE_ADDR") or None


def _safe_next(request):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return reverse("storefront:home")


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    form = PhoneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            request_otp(form.cleaned_data["phone_number"], _ip(request))
        except OTPRateLimited:
            messages.error(request, "درخواست‌های پیاپی زیاد است. کمی بعد دوباره تلاش کنید.")
        except SMSProviderError:
            messages.error(request, "ارسال کد در حال حاضر ممکن نیست. کمی بعد دوباره تلاش کنید.")
        else:
            request.session["otp_pending_phone"] = form.cleaned_data["phone_number"]
            request.session["otp_pending_remember"] = form.cleaned_data["remember_me"]
            request.session["otp_pending_next"] = _safe_next(request)
            messages.info(request, "اگر سرویس پیامک در دسترس باشد، کد ورود ارسال می‌شود.")
            return redirect("account:verify")
    return render(request, "account/login.html", {"form": form, "next": _safe_next(request)})


@require_http_methods(["GET", "POST"])
def verify_view(request):
    phone = request.session.get("otp_pending_phone")
    if not phone:
        return redirect("account:login")
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            valid = verify_otp(phone, form.cleaned_data["code"], _ip(request))
        except OTPRateLimited:
            valid = False
        if not valid:
            form.add_error("code", "کد معتبر نیست یا مهلت آن به پایان رسیده است.")
        else:
            user = User.objects.filter(phone_number=phone).first()
            if user is None:
                try:
                    user = User.objects.create_user(phone_number=phone, is_active=True)
                except IntegrityError:
                    user = User.objects.get(phone_number=phone)
            if not user.is_active:
                form.add_error(None, "ورود این حساب امکان‌پذیر نیست.")
            else:
                remember = request.session.get("otp_pending_remember", False)
                target = request.session.get("otp_pending_next") or reverse("account:profile")
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                request.session.set_expiry(60 * 60 * 24 * 30 if remember else 0)
                for key in ("otp_pending_phone", "otp_pending_remember", "otp_pending_next"):
                    request.session.pop(key, None)
                from commerce.services import merge_guest_cart
                merge_guest_cart(request, user)
                messages.success(request, "با موفقیت وارد شدید.")
                return redirect(target)
    from django.conf import settings
    from .models import OTPChallenge
    latest = OTPChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
    cooldown = 0
    if latest:
        elapsed = (timezone.now() - latest.created_at).total_seconds()
        cooldown = max(0, int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed))
    return render(request, "account/verify.html", {
        "form": form, "phone": phone, "next": request.session.get("otp_pending_next"),
        "resend_cooldown": cooldown,
    })


@require_POST
def resend_otp(request):
    phone = request.session.get("otp_pending_phone")
    if not phone:
        return redirect("account:login")
    try:
        request_otp(phone, _ip(request))
    except (OTPRateLimited, SMSProviderError):
        messages.error(request, "فعلاً امکان ارسال دوبارهٔ کد نیست. کمی بعد تلاش کنید.")
    else:
        messages.info(request, "اگر سرویس پیامک در دسترس باشد، کد تازه ارسال می‌شود.")
    return redirect("account:verify")


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "از حساب خارج شدید.")
    return redirect("storefront:home")


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات حساب ذخیره شد.")
        return redirect("account:profile")
    return render(request, "account/profile.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def address_list(request):
    form = AddressForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        if not request.user.addresses.exists():
            address.is_default = True
        address.save()
        messages.success(request, "نشانی ذخیره شد.")
        return redirect("account:addresses")
    addresses = request.user.addresses.all()
    return render(request, "account/addresses.html", {"form": form, "addresses": addresses})


@login_required
@require_http_methods(["GET", "POST"])
def address_edit(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    form = AddressForm(request.POST or None, instance=address)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "نشانی ویرایش شد.")
        return redirect("account:addresses")
    return render(request, "account/address_form.html", {"form": form, "address": address})


@login_required
@require_POST
def address_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.is_default = True
    address.save(update_fields=("is_default", "updated_at"))
    messages.success(request, "نشانی پیش‌فرض تغییر کرد.")
    return redirect("account:addresses")


@login_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = address.is_default
    with transaction.atomic():
        request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
        address.delete()
        if was_default:
            replacement = request.user.addresses.order_by("-updated_at", "-pk").first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=("is_default", "updated_at"))
    messages.success(request, "نشانی حذف شد.")
    return redirect("account:addresses")


@login_required
@require_http_methods(["GET", "POST"])
def deletion_request(request):
    form = AccountDeletionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        AccountDeletionRequest.objects.get_or_create(
            user=request.user,
            status=AccountDeletionRequest.Status.REQUESTED,
            defaults={"reason": form.cleaned_data["reason"]},
        )
        messages.success(request, "درخواست حریم خصوصی ثبت شد تا توسط مدیر بررسی شود.")
        return redirect("account:profile")
    return render(request, "account/deletion_request.html", {"form": form})
