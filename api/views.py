"""
REST API views (section 17).

Read endpoints are public; cart/wishlist/orders/review writes require
authentication. Private user data (other users' emails, profiles) is never
serialised.
"""
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from cart.services import CartError, get_cart
from orders.models import Order
from products.models import Brand, Category, Product, search_products
from reviews.models import Review
from reviews.services import submit_review
from wishlist.models import WishlistItem

from .filters import ProductFilterSet
from .serializers import (
    BrandSerializer,
    CartSerializer,
    CategorySerializer,
    OrderSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
    WishlistSerializer,
)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Public catalog with search, filters and ordering."""

    serializer_class = ProductListSerializer
    filterset_class = ProductFilterSet
    search_fields = ['name', 'description', 'short_description', 'sku',
                     'brand__name', 'category__name']
    ordering_fields = ['created_at', 'price', 'sale_price', 'total_sales', 'name']
    ordering = ['-created_at']
    lookup_field = 'slug'

    def get_queryset(self):
        qs = (
            Product.objects.listed()
            .select_related('category', 'brand')
            .prefetch_related('images')
        )
        term = self.request.query_params.get('q') or self.request.query_params.get('search')
        if term:
            qs = search_products(qs, term)
        ordering = self.request.query_params.get('ordering', '')
        if ordering.lstrip('-') == 'effective_price':
            from django.db.models import (
                Case, DecimalField, ExpressionWrapper, F, When,
            )

            qs = qs.annotate(
                effective_sort_price=ExpressionWrapper(
                    Case(
                        When(sale_price__isnull=False, then=F('sale_price')),
                        default=F('price'),
                    ),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                ),
            )
            qs = qs.order_by(('-' if ordering.startswith('-') else '') + 'effective_sort_price')
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True).annotate(
        product_count=Count('products', filter=Q(products__is_active=True)),
    )
    serializer_class = CategorySerializer
    lookup_field = 'slug'


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Brand.objects.filter(is_active=True).annotate(
        product_count=Count('products', filter=Q(products__is_active=True)),
    )
    serializer_class = BrandSerializer
    lookup_field = 'slug'


class OrderListAPIView(generics.ListAPIView):
    """A customer sees only their own orders."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related('items')
            .order_by('-created_at')
        )


class OrderDetailAPIView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'order_number'

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


@api_view(['GET', 'POST', 'PATCH', 'DELETE'])
def cart_api(request):
    """
    Session-aware cart API.
    GET    - current cart contents
    POST   - add {product_id, variant_id?, quantity?}
    PATCH  - update {product_id, variant_id?, quantity}
    DELETE - remove {product_id, variant_id?} (body or query params)
    """
    cart = get_cart(request)

    try:
        if request.method == 'GET':
            return Response(CartSerializer(cart.to_dict()).data)

        if request.method == 'POST':
            product = get_object_or_404(
                Product.objects.listed(), pk=request.data.get('product_id'),
            )
            variant = None
            variant_id = request.data.get('variant_id')
            if variant_id:
                variant = product.variants.filter(pk=variant_id, is_active=True).first()
                if variant is None:
                    return Response({'detail': 'Invalid variant.'}, status=400)
            quantity = int(request.data.get('quantity', 1))
            cart.add(product, variant, quantity)
            return Response(CartSerializer(cart.to_dict()).data, status=201)

        if request.method == 'PATCH':
            product_id = request.data.get('product_id')
            variant_id = request.data.get('variant_id') or None
            quantity = int(request.data.get('quantity', 0))
            cart.update(product_id, variant_id, quantity)
            return Response(CartSerializer(cart.to_dict()).data)

        if request.method == 'DELETE':
            product_id = (request.data.get('product_id')
                          or request.query_params.get('product_id'))
            variant_id = (request.data.get('variant_id')
                          or request.query_params.get('variant_id'))
            cart.remove(product_id, int(variant_id) if variant_id else None)
            return Response(CartSerializer(cart.to_dict()).data)
    except (CartError, ValueError, TypeError) as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def wishlist_api(request):
    """GET list / POST {product_id} add / DELETE {product_id} remove."""
    if request.method == 'GET':
        items = WishlistItem.objects.filter(user=request.user).select_related('product')
        return Response(WishlistSerializer(items, many=True).data)

    product_id = request.data.get('product_id')
    if not product_id:
        return Response({'detail': 'product_id is required.'}, status=400)
    product = get_object_or_404(Product, pk=product_id)
    if request.method == 'POST':
        _, created = WishlistItem.objects.get_or_create(
            user=request.user, product=product,
        )
        return Response(
            {'detail': 'Added to wishlist.' if created else 'Already in wishlist.'},
            status=201 if created else 200,
        )
    # DELETE
    deleted, _ = WishlistItem.objects.filter(user=request.user, product=product).delete()
    if not deleted:
        return Response({'detail': 'Not in wishlist.'}, status=404)
    return Response({'detail': 'Removed from wishlist.'})


@api_view(['GET'])
def product_reviews_api(request, slug: str):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    reviews = Review.objects.for_product(product)
    return Response({
        'rating': product.rating_summary(),
        'results': ReviewSerializer(reviews, many=True).data,
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def review_create_api(request):
    serializer = ReviewCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    product = get_object_or_404(
        Product.objects.listed(), slug=serializer.validated_data['product_slug'],
    )
    try:
        review = submit_review(
            user=request.user,
            product=product,
            rating=serializer.validated_data['rating'],
            title=serializer.validated_data['title'],
            text=serializer.validated_data['text'],
        )
    except PermissionError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
    return Response(ReviewSerializer(review).data, status=201)
