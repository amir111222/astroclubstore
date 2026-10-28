import uuid

from django import forms

from account.models import Address


class CheckoutForm(forms.Form):
    address = forms.ModelChoiceField(queryset=Address.objects.none(), label="نشانی ارسال")
    coupon_code = forms.CharField(label="کد تخفیف", required=False, max_length=40)
    quote_token = forms.CharField(widget=forms.HiddenInput())
    checkout_key = forms.UUIDField(widget=forms.HiddenInput(), initial=uuid.uuid4)

    def __init__(self, *args, user, needs_address=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.needs_address = needs_address
        self.fields["address"].required = needs_address
        self.fields["address"].queryset = user.addresses.all()
        default = user.addresses.filter(is_default=True).first() or user.addresses.first()
        if default and not self.is_bound:
            self.fields["address"].initial = default


class CancellationForm(forms.Form):
    reason = forms.CharField(label="دلیل درخواست", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 3}))


class OrderStatusForm(forms.Form):
    from .models import Order
    status = forms.ChoiceField(label="وضعیت جدید", choices=Order.Status.choices)
    tracking_number = forms.CharField(label="شمارهٔ پیگیری", max_length=120, required=False)
