import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from .phone import normalize_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("A phone number is required.")
        user = self.model(phone_number=normalize_phone(phone_number), **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusers must have staff and superuser privileges.")
        if not password:
            raise ValueError("A password is required when creating a superuser.")
        return self.create_user(phone_number, password, **extra_fields)


class User(AbstractUser):
    username = None
    phone_number = models.CharField(max_length=13, unique=True, db_index=True)
    email = models.EmailField(blank=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def save(self, *args, **kwargs):
        self.phone_number = normalize_phone(self.phone_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.phone_number


class Address(models.Model):
    user = models.ForeignKey("account.User", on_delete=models.CASCADE, related_name="addresses")
    recipient_name = models.CharField("نام گیرنده", max_length=120)
    recipient_phone = models.CharField("تلفن گیرنده", max_length=13)
    province = models.CharField("استان", max_length=80)
    city = models.CharField("شهر", max_length=80)
    postal_code = models.CharField("کد پستی", max_length=10)
    address = models.CharField("نشانی", max_length=500)
    details = models.CharField("جزئیات نشانی", max_length=250, blank=True)
    is_default = models.BooleanField("نشانی پیش‌فرض", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_default", "-updated_at")
        constraints = [
            models.UniqueConstraint(fields=("user",), condition=Q(is_default=True), name="one_default_address_per_user"),
        ]

    def save(self, *args, **kwargs):
        self.recipient_phone = normalize_phone(self.recipient_phone)
        if self.is_default:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=self.user_id)
                Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.city}، {self.recipient_name}"


class OTPChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=13, db_index=True)
    code_digest = models.CharField(max_length=64)
    requested_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    delivered = models.BooleanField(default=False)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("phone_number", "created_at"))]


class OTPThrottle(models.Model):
    key_digest = models.CharField(max_length=64, unique=True)
    window_started_at = models.DateTimeField(default=timezone.now)
    count = models.PositiveSmallIntegerField(default=0)


class AccountDeletionRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "درخواست‌شده"
        REVIEWING = "reviewing", "در حال بررسی"
        COMPLETED = "completed", "انجام‌شده"
        REJECTED = "rejected", "ردشده"

    user = models.ForeignKey("account.User", on_delete=models.PROTECT, related_name="deletion_requests")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
