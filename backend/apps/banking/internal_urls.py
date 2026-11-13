from django.urls import path

from .internal_views import (
    InternalAccountInfoView,
    InternalAccountLookupView,
    InternalBalanceView,
    InternalDashboardSummaryView,
    InternalStatementView,
    InternalTransactionLookupView,
    InternalTransactionsView,
)

urlpatterns = [
    path('balance/', InternalBalanceView.as_view(), name='internal-banking-balance'),
    path('account-info/', InternalAccountInfoView.as_view(), name='internal-banking-account-info'),
    path('transactions/', InternalTransactionsView.as_view(), name='internal-banking-transactions'),
    path('transactions/lookup/', InternalTransactionLookupView.as_view(), name='internal-banking-transaction-lookup'),
    path('statement/', InternalStatementView.as_view(), name='internal-banking-statement'),
    path('account-lookup/', InternalAccountLookupView.as_view(), name='internal-banking-account-lookup'),
    path('dashboard-summary/', InternalDashboardSummaryView.as_view(), name='internal-banking-dashboard-summary'),
]

