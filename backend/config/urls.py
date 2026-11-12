from django.contrib import admin
from django.urls import include, path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    return Response({'status': 'ok'})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health/', health_check, name='health-check'),
    path('api/v1/auth/', include('apps.accounts.auth_urls')),
    path('api/v1/', include('apps.accounts.urls')),
    path('api/v1/banking/', include('apps.banking.urls')),
    path('api/v1/cheque/', include('apps.cheque.urls')),
    path('api/v1/endorsements/', include('apps.endorsement.urls')),
    path('api/v1/chat/', include('apps.chat.urls')),
    # Internal service-to-service endpoints (MCP servers only)
    path('internal/banking/', include('apps.banking.internal_urls')),
    path('internal/service/', include('apps.cheque.internal_urls')),
    path('internal/service/', include('apps.accounts.internal_urls')),
    # OpenAPI Schema & Swagger UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path(
        'api/schema/swagger-ui/',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui',
    ),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

