"""Account forms: registration, login, profile, address management."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError

from core.validators import validate_image, validate_phone_10_digits

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
        label='Phone number',
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'inputmode': 'numeric',
            'autocomplete': 'tel',
            'maxlength': '10',
            'pattern': '[0-9]{10}',
            'placeholder': '9876543210',
        }),
        help_text='10-digit mobile number.',
        error_messages={'required': 'Enter your 10-digit phone number.'},
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone')

    #: Django compares password1 and password2 in ``clean_password2``; make the
    #: mismatch message explicit so the form cannot be submitted until they match.
    error_messages = {
        **UserCreationForm.error_messages,
        'password_mismatch': 'The two passwords do not match. Please re-enter them.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].label = 'Password'
        self.fields['password2'].label = 'Confirm your password'
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})

    def clean_email(self) -> str:
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email

    def clean_phone(self) -> str:
        """Reject anything that is not a 10-digit number and store the digits."""
        return validate_phone_10_digits(self.cleaned_data['phone'])

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


DEFAULT_COUNTRY = 'India'

#: Countries offered in the address form. India is first so it is the default.
COUNTRY_CHOICES = [
    ('India', 'India'),
    ('United States', 'United States'),
    ('United Kingdom', 'United Kingdom'),
    ('United Arab Emirates', 'United Arab Emirates'),
    ('Australia', 'Australia'),
    ('Canada', 'Canada'),
    ('Singapore', 'Singapore'),
    ('Malaysia', 'Malaysia'),
    ('Nepal', 'Nepal'),
    ('Bangladesh', 'Bangladesh'),
    ('Sri Lanka', 'Sri Lanka'),
    ('Saudi Arabia', 'Saudi Arabia'),
    ('South Africa', 'South Africa'),
    ('Germany', 'Germany'),
    ('France', 'France'),
    ('Netherlands', 'Netherlands'),
    ('Japan', 'Japan'),
    ('China', 'China'),
    ('New Zealand', 'New Zealand'),
]


class AddressForm(forms.ModelForm):
    country = forms.ChoiceField(
        choices=COUNTRY_CHOICES,
        initial=DEFAULT_COUNTRY,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

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
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A previously saved country that is not in the list must stay
        # selectable, otherwise editing the address would silently change it.
        saved_country = self.instance.country if self.instance.pk else None
        if saved_country and saved_country not in dict(self.fields['country'].choices):
            self.fields['country'].choices = [
                *self.fields['country'].choices, (saved_country, saved_country),
            ]
        if not self.is_bound:
            self.initial.setdefault('country', saved_country or DEFAULT_COUNTRY)


class ChangePasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
