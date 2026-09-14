"""Core views: homepage, static pages, contact and error handlers."""
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from products.models import Category, Product

from .emails import send_templated_email
from .forms import ContactForm
from .utils import rate_limit


def home(request: HttpRequest) -> HttpResponse:
    """Landing page: hero, categories, featured products, new arrivals, sale."""
    context = {
        'categories': Category.objects.filter(is_active=True),
        'featured_products': Product.objects.listed().filter(featured=True)[:8],
        'new_arrivals': Product.objects.listed().order_by('-created_at')[:8],
        'sale_products': Product.objects.listed().on_sale()[:8],
        'popular_products': Product.objects.listed().order_by('-total_sales')[:4],
    }
    return render(request, 'core/home.html', context)


def about(request: HttpRequest) -> HttpResponse:
    return render(request, 'core/about.html')


def terms(request: HttpRequest) -> HttpResponse:
    return render(request, 'core/terms.html')


def privacy(request: HttpRequest) -> HttpResponse:
    return render(request, 'core/privacy.html')


@rate_limit('contact', limit=5, per_seconds=600)
@require_POST
def contact_submit(request: HttpRequest) -> HttpResponse:
    """Handle the contact form POST (used by the contact page)."""
    form = ContactForm(request.POST)
    if form.is_valid():
        message = form.save()
        send_templated_email(
            'emails/contact_admin_subject.txt',
            'emails/contact_admin.txt',
            {'message': message},
            settings.ADMIN_EMAIL_NOTIFICATIONS,
        )
        return redirect('core:contact_success')
    # Invalid submissions re-render the contact page with errors.
    return render(request, 'core/contact.html', {'form': form}, status=400)


def contact(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        return contact_submit(request)
    return render(request, 'core/contact.html', {'form': ContactForm()})


def contact_success(request: HttpRequest) -> HttpResponse:
    return render(request, 'core/contact_success.html')


def health(request: HttpRequest) -> HttpResponse:
    """Minimal liveness probe for load balancers / container healthchecks."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    from django.http import JsonResponse

    return JsonResponse({'status': 'ok' if db_ok else 'degraded',
                         'database': db_ok}, status=status)


# ---------------------------------------------------------------------------
# Error handlers (section 20). Never leak exception details.
# ---------------------------------------------------------------------------
def bad_request(request, exception=None):
    return render(request, 'errors/400.html', status=400)


def forbidden(request, exception=None):
    return render(request, 'errors/403.html', status=403)


def page_not_found(request, exception=None):
    return render(request, 'errors/404.html', status=404)


def server_error(request):
    return render(request, 'errors/500.html', status=500)
