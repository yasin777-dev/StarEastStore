from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'api'

router = DefaultRouter()
router.register('products', views.ProductViewSet, basename='product')
router.register('categories', views.CategoryViewSet, basename='category')
router.register('brands', views.BrandViewSet, basename='brand')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/token/', obtain_auth_token, name='api_token'),
    path('cart/', views.cart_api, name='api_cart'),
    path('wishlist/', views.wishlist_api, name='api_wishlist'),
    path('orders/', views.OrderListAPIView.as_view(), name='api_orders'),
    path('orders/<str:order_number>/', views.OrderDetailAPIView.as_view(), name='api_order_detail'),
    path('products/<str:slug>/reviews/', views.product_reviews_api, name='api_product_reviews'),
    path('reviews/create/', views.review_create_api, name='api_review_create'),
]
