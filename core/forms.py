"""Contact form with basic validation and a honeypot for bots."""
from django import forms

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    # Hidden honeypot: must stay empty (bots fill every field they see).
    website = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'autocomplete': 'off'}),
    )

    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 120}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 200}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
        }

    def clean_website(self) -> str:
        if self.cleaned_data.get('website'):
            raise forms.ValidationError('Spam detected.')
        return ''

    def clean_message(self) -> str:
        message = self.cleaned_data.get('message', '')
        if len(message.strip()) < 10:
            raise forms.ValidationError('Please write a slightly longer message.')
        return message.strip()
