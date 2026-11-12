from django.urls import path

from .internal_views import (
    InternalAccountInfoView,
    InternalBalanceView,
    InternalStatementView,
    InternalTransactionsView,
)

urlpatterns = [
    path('balance/', InternalBalanceView.as_view(), name='internal-banking-balance'),
    path('account-info/', InternalAccountInfoView.as_view(), name='internal-banking-account-info'),
    path('transactions/', InternalTransactionsView.as_view(), name='internal-banking-transactions'),
    path('statement/', InternalStatementView.as_view(), name='internal-banking-statement'),
]

