"""Checkout form."""
from django import forms

from accounts.models import Address

from .models import ShippingMethod


class CheckoutForm(forms.Form):
    address_id = forms.ModelChoiceField(
        label='Shipping address', queryset=Address.objects.none(),
        widget=forms.HiddenInput,
        error_messages={
            'required': 'Please select a shipping address.',
            'invalid_choice': 'Please select one of your saved shipping addresses.',
        },
    )
    shipping_method = forms.ModelChoiceField(
        queryset=ShippingMethod.objects.filter(is_active=True),
        widget=forms.RadioSelect, empty_label=None,
        error_messages={
            'required': 'Please select a shipping method.',
            'invalid_choice': 'This shipping method is no longer available. Please choose another.',
        },
    )
    coupon_code = forms.CharField(
        max_length=40, required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'Enter coupon code',
        }),
    )
    payment_method = forms.ChoiceField(
        widget=forms.RadioSelect,
        error_messages={
            'required': 'Please select a payment method.',
            'invalid_choice': 'Please select an available payment method.',
        },
    )
    customer_note = forms.CharField(
        required=False, max_length=500,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def __init__(self, *args, user=None, available_payment_methods=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['address_id'].queryset = user.addresses.all()
            self.fields['address_id'].widget.attrs['data-address-source'] = 'user'
        self.fields['payment_method'].choices = available_payment_methods or []
