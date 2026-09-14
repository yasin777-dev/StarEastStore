from django.urls import path

from . import views

app_name = 'products'

urlpatterns = [
    path('shop/', views.product_list, name='list'),
    path('search/', views.product_list, name='search'),
    path('sale/', views.sale_products, name='sale'),
    path('category/<slug:slug>/', views.category_detail, name='category'),
    path('brand/<slug:slug>/', views.brand_detail, name='brand'),
    path('product/<slug:slug>/', views.product_detail, name='detail'),
]
