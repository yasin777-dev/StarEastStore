"""Checkout form."""
from django import forms

from .models import ShippingMethod


class CheckoutForm(forms.Form):
    address_id = forms.IntegerField(widget=forms.HiddenInput)
    shipping_method = forms.ModelChoiceField(
        queryset=ShippingMethod.objects.filter(is_active=True),
        widget=forms.RadioSelect, empty_label=None,
    )
    coupon_code = forms.CharField(
        max_length=40, required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'Enter coupon code',
        }),
    )
    payment_method = forms.ChoiceField(widget=forms.RadioSelect)
    customer_note = forms.CharField(
        required=False, max_length=500,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def __init__(self, *args, user=None, available_payment_methods=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['address_id'].widget.attrs['data-address-source'] = 'user'
        if available_payment_methods:
            self.fields['payment_method'].choices = available_payment_methods
