from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AccountLookupView,
    CustomerAccountManageView,
    CustomerDetailView,
    CustomerListView,
    DepositView,
    MyBankAccountView,
    StaffDashboardSummaryView,
    TellerDepositView,
    TellerWithdrawView,
    TransactionViewSet,
    TransferView,
    WithdrawView,
)

router = DefaultRouter()
router.register('transactions', TransactionViewSet, basename='transaction')

urlpatterns = [
    path('account/', MyBankAccountView.as_view(), name='banking-account'),
    path('lookup/', AccountLookupView.as_view(), name='banking-lookup'),
    path('deposit/', DepositView.as_view(), name='banking-deposit'),
    path('withdraw/', WithdrawView.as_view(), name='banking-withdraw'),
    path('transfer/', TransferView.as_view(), name='banking-transfer'),
    path('dashboard-summary/', StaffDashboardSummaryView.as_view(), name='banking-dashboard-summary'),
    path('customers/', CustomerListView.as_view(), name='banking-customer-list'),
    path('customers/<int:user_id>/', CustomerDetailView.as_view(), name='banking-customer-detail'),
    path(
        'customers/<int:user_id>/account/',
        CustomerAccountManageView.as_view(),
        name='banking-customer-account',
    ),
    path(
        'customers/<int:user_id>/deposit/',
        TellerDepositView.as_view(),
        name='banking-teller-deposit',
    ),
    path(
        'customers/<int:user_id>/withdraw/',
        TellerWithdrawView.as_view(),
        name='banking-teller-withdraw',
    ),
    path('', include(router.urls)),
]

