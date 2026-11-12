from django.urls import path

from .internal_views import InternalChequeRequestCreateView

urlpatterns = [
    path(
        'cheque-request/',
        InternalChequeRequestCreateView.as_view(),
        name='internal-service-cheque-request',
    ),
]

