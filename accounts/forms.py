"""Account forms: registration, login, profile, address management."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError

from core.validators import validate_image

from .models import Address, CustomerProfile

User = get_user_model()


class RegisterForm(UserCreationForm):
    """Customer sign-up with email as the primary identifier."""

    email = forms.EmailField(
        label='Email address',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autofocus': True}),
    )
    first_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    phone = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})

    def clean_email(self) -> str:
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email

    def save(self, commit: bool = True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data.get('phone', '')
        if not user.username:
            user.username = User.objects.username_for(user.email)
        if commit:
            user.save()
            # Keep the profile phone in sync with registration data.
            profile = user.profile
            if not profile.phone:
                profile.phone = user.phone
                profile.save(update_fields=['phone'])
        return user


class EmailAuthenticationForm(AuthenticationForm):
    """Login form accepting email (or username) + password."""

    username = forms.CharField(
        label='Email address',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autofocus': True}),
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Please enter a correct email address and password.',
    }


class ProfileForm(forms.ModelForm):
    """Edit the customer profile (and the mirrored user fields)."""

    first_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = CustomerProfile
        fields = ['image', 'phone', 'date_of_birth']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['first_name'].initial = self.user.first_name
        self.fields['last_name'].initial = self.user.last_name
        self.fields['email'].initial = self.user.email
        self.fields['image'].validators.append(validate_image)

    def clean_email(self) -> str:
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise ValidationError('This email is already used by another account.')
        return email

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'content_type'):
            validate_image(image)
        return image

    def save(self, commit: bool = True):
        profile = super().save(commit=False)
        user = self.user
        user.first_name = self.cleaned_data['first_name'].strip()
        user.last_name = self.cleaned_data['last_name'].strip()
        user.email = self.cleaned_data['email']
        user.phone = profile.phone
        user.save()
        if commit:
            profile.save()
        return profile


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            'full_name', 'phone', 'address_line_1', 'address_line_2',
            'city', 'state', 'postal_code', 'country', 'is_default',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line_1': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line_2': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ChangePasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
