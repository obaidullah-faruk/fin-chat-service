from django.urls import path

from .internal_views import InternalAddressUpdateView, InternalCustomerLookupView, InternalKYCStatusView

urlpatterns = [
    path('address/', InternalAddressUpdateView.as_view(), name='internal-service-address'),
    path('kyc-status/', InternalKYCStatusView.as_view(), name='internal-service-kyc-status'),
    path('customer-lookup/', InternalCustomerLookupView.as_view(), name='internal-service-customer-lookup'),
]

