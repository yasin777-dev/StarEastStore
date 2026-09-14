from django.urls import path

from . import views

app_name = 'reviews'

urlpatterns = [
    path('product/<slug:product_slug>/add/', views.add_review, name='add'),
]
