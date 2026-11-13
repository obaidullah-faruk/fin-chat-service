from django.urls import path

from .internal_views import InternalChequeRequestCreateView, InternalPendingReviewsView

urlpatterns = [
    path(
        'cheque-request/',
        InternalChequeRequestCreateView.as_view(),
        name='internal-service-cheque-request',
    ),
    path(
        'pending-reviews/',
        InternalPendingReviewsView.as_view(),
        name='internal-service-pending-reviews',
    ),
]

