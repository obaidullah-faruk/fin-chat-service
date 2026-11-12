from django.urls import path

from .internal_views import InternalAddressUpdateView, InternalKYCStatusView

urlpatterns = [
    path('address/', InternalAddressUpdateView.as_view(), name='internal-service-address'),
    path('kyc-status/', InternalKYCStatusView.as_view(), name='internal-service-kyc-status'),
]

