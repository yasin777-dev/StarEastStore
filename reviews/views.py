"""Review submission views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from products.models import Product

from .forms import ReviewForm
from .services import submit_review


@login_required
@require_POST
def add_review(request, product_slug: str) -> HttpResponse:
    product = get_object_or_404(Product, slug=product_slug, is_active=True)
    form = ReviewForm(request.POST)
    if form.is_valid():
        try:
            submit_review(
                user=request.user,
                product=product,
                rating=form.cleaned_data['rating'],
                title=form.cleaned_data['title'],
                text=form.cleaned_data['text'],
            )
            messages.success(request, 'Thanks! Your review has been published.')
        except PermissionError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(
            request,
            'Please fix the review errors: ' + '; '.join(
                f'{field}: {", ".join(errors)}'
                for field, errors in form.errors.items()
            ),
        )
    return redirect('products:detail', slug=product_slug)
