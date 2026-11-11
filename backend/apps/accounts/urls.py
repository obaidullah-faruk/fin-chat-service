from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ActivityLogViewSet, AddressViewSet, RoleListView, UserViewSet

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('addresses', AddressViewSet, basename='address')
router.register('activities', ActivityLogViewSet, basename='activity')

urlpatterns = [
    path('roles/', RoleListView.as_view(), name='role-list'),
    path('', include(router.urls)),
]

