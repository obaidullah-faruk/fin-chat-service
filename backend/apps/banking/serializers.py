from decimal import Decimal
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import CustomUser
from apps.accounts.serializers import (
    ActivityLogSerializer,
    AddressSerializer,
    UserSerializer,
)
from .models import BankAccount, Transaction


FUNDING_SOURCE_LABELS = {
    'bank_transfer': 'External Bank Transfer Deposit',
    'debit_card': 'Debit Card Top-Up Deposit',
    'atm_cash': 'ATM Cash Deposit',
    'mobile_wallet': 'Mobile Check / Wallet Deposit',
}

WITHDRAWAL_METHOD_LABELS = {
    'atm_cash': 'ATM Cash Withdrawal',
    'bank_transfer': 'External Bank Transfer Withdrawal',
    'debit_card': 'Debit Card Payout Withdrawal',
}


class BankAccountSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    owner_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = BankAccount
        fields = [
            'id',
            'account_number',
            'account_type',
            'balance',
            'currency',
            'is_usd_endorsed',
            'usd_endorsement_limit',
            'is_active',
            'username',
            'owner_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'account_number',
            'balance',
            'currency',
            'is_usd_endorsed',
            'usd_endorsement_limit',
            'is_active',
            'created_at',
            'updated_at',
        ]


class BankAccountUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ['account_type']


class AmountDescriptionSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal('0.00'):
            raise serializers.ValidationError('Amount must be greater than zero.')
        return value


class DepositSerializer(AmountDescriptionSerializer):
    funding_source = serializers.ChoiceField(
        choices=list(FUNDING_SOURCE_LABELS.items()),
        required=False,
        default='bank_transfer',
    )


class WithdrawSerializer(AmountDescriptionSerializer):
    withdrawal_method = serializers.ChoiceField(
        choices=list(WITHDRAWAL_METHOD_LABELS.items()),
        required=False,
        default='atm_cash',
    )


class TellerOperationSerializer(AmountDescriptionSerializer):
    pass


class StaffAccountUpdateSerializer(serializers.Serializer):
    account_type = serializers.ChoiceField(choices=BankAccount.AccountType.choices, required=False)
    is_active = serializers.BooleanField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if 'account_type' not in attrs and 'is_active' not in attrs:
            raise serializers.ValidationError('Provide account_type or is_active to update.')
        return attrs


class TransferSerializer(AmountDescriptionSerializer):
    to_account_number = serializers.CharField(max_length=20)

    def validate_to_account_number(self, value: str) -> str:
        return value.strip().upper()


class TransactionSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='account.user_id', read_only=True)
    account_number = serializers.CharField(source='account.account_number', read_only=True)
    username = serializers.CharField(source='account.user.username', read_only=True)
    owner_name = serializers.CharField(source='account.user.full_name', read_only=True)
    related_account_number = serializers.CharField(
        source='related_account.account_number', read_only=True, default=None
    )
    related_username = serializers.CharField(
        source='related_account.user.username', read_only=True, default=None
    )
    performed_by_username = serializers.CharField(
        source='performed_by.username', read_only=True, default=None
    )

    class Meta:
        model = Transaction
        fields = [
            'id',
            'reference',
            'user_id',
            'account_number',
            'username',
            'owner_name',
            'related_account_number',
            'related_username',
            'performed_by',
            'performed_by_username',
            'transaction_type',
            'channel',
            'amount',
            'balance_after',
            'description',
            'created_at',
        ]


class AccountLookupSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    owner_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = BankAccount
        fields = ['account_number', 'account_type', 'username', 'owner_name']


class CustomerListSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source='role.name', read_only=True)
    full_name = serializers.CharField(read_only=True)
    bank_account = serializers.SerializerMethodField()
    transaction_count = serializers.IntegerField(read_only=True, default=0)
    pending_cheques = serializers.IntegerField(read_only=True, default=0)
    pending_endorsements = serializers.IntegerField(read_only=True, default=0)
    addresses_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'phone',
            'role',
            'is_active',
            'created_at',
            'bank_account',
            'transaction_count',
            'pending_cheques',
            'pending_endorsements',
            'addresses_count',
        ]

    @extend_schema_field(BankAccountSerializer(allow_null=True))
    def get_bank_account(self, obj):
        account = getattr(obj, 'bank_account', None)
        if not account:
            return None
        return BankAccountSerializer(account).data


class CustomerStatsSerializer(serializers.Serializer):
    total_deposits = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_withdrawals = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_transfers_in = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_transfers_out = serializers.DecimalField(max_digits=15, decimal_places=2)
    transaction_count = serializers.IntegerField()
    pending_cheques = serializers.IntegerField()
    pending_endorsements = serializers.IntegerField()
    activity_count = serializers.IntegerField()
    last_transaction_at = serializers.DateTimeField(allow_null=True)
    last_activity_at = serializers.DateTimeField(allow_null=True)


class CustomerDetail360Serializer(serializers.Serializer):
    user = UserSerializer()
    bank_account = BankAccountSerializer(allow_null=True)
    addresses = AddressSerializer(many=True)
    stats = CustomerStatsSerializer()


class StaffDashboardSummarySerializer(serializers.Serializer):
    total_customers = serializers.IntegerField()
    total_bank_accounts = serializers.IntegerField()
    active_accounts = serializers.IntegerField()
    frozen_accounts = serializers.IntegerField()
    usd_endorsed_accounts = serializers.IntegerField()
    total_liquidity = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_transactions = serializers.IntegerField()
    pending_cheques = serializers.IntegerField()
    pending_endorsements = serializers.IntegerField()
    recent_transactions = TransactionSerializer(many=True)
    recent_activities = ActivityLogSerializer(many=True)
