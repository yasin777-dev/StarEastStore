from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),
    path('orders/', views.order_list, name='list'),
    path('orders/<str:order_number>/', views.order_detail, name='detail'),
    path('orders/<str:order_number>/cancel/', views.order_cancel, name='cancel'),
]
