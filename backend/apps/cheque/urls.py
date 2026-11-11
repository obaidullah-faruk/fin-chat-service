from django.urls import path

from .views import ChequeBookRequestCreateView, ChequeBookRequestListView, ChequeBookReviewView

urlpatterns = [
    path('request/', ChequeBookRequestCreateView.as_view(), name='cheque-request-create'),
    path('requests/', ChequeBookRequestListView.as_view(), name='cheque-request-list'),
    path('requests/<int:pk>/review/', ChequeBookReviewView.as_view(), name='cheque-request-review'),
]

