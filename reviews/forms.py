"""Review submission form."""
from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'title', 'text']
        widgets = {
            'rating': forms.Select(
                choices=[(i, f'{i} star{"s" if i > 1 else ""}') for i in range(1, 6)],
                attrs={'class': 'form-select'},
            ),
            'title': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 150}),
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
