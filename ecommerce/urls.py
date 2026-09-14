"""
URL configuration for the StarEastStore project.

Section 20 (error handling) maps Django's handler hooks to branded templates.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.decorators.http import require_safe
from django.views.static import serve

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
]

# User uploads (product images, brand logos, avatars).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    # Platforms without a separate web server (Render's native runtime has no
    # nginx) still need /media/ served, otherwise every uploaded image 404s.
    # WhiteNoise only covers STATIC_URL, so serve them from Django here; for a
    # high-traffic store set SERVE_MEDIA=False and use object storage (S3,
    # Cloudinary...) or attach a disk + reverse proxy.
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'),
            require_safe(serve),
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
