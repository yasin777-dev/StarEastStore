from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('simulate/<str:reference>/', views.simulate_payment, name='simulate'),
    path('simulate/<str:reference>/process/', views.simulate_process, name='simulate_process'),
    path('verify/<str:reference>/', views.verify_payment, name='verify'),
    path('cancel/<str:reference>/', views.cancel_payment_view, name='cancel'),
    path('retry/<str:order_number>/', views.retry_payment_view, name='retry'),
    path('webhook/<str:gateway_code>/', views.webhook, name='webhook'),
]
