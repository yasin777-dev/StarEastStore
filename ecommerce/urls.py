"""
URL configuration for the StarEastStore project.

Section 20 (error handling) maps Django's handler hooks to branded templates.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from .admin_site import admin_site

handler400 = 'core.views.bad_request'
handler403 = 'core.views.forbidden'
handler404 = 'core.views.page_not_found'
handler500 = 'core.views.server_error'

urlpatterns = [
    path('', include('core.urls')),
    path('admin/', admin_site.urls),
    path('accounts/', include('accounts.urls')),
    path('', include('products.urls')),
    path('cart/', include('cart.urls')),
    path('', include('orders.urls')),
    path('payment/', include('payments.urls')),
    path('reviews/', include('reviews.urls')),
    path('wishlist/', include('wishlist.urls')),
    path('api/', include('api.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
