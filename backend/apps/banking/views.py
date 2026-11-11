import logging
import uuid
from decimal import Decimal
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, generics, status, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.audit import record_activity
from apps.accounts.models import ActivityLog, Address, CustomUser
from apps.cheque.models import ChequeBookRequest
from apps.endorsement.models import Endorsement
from core.permissions import (
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_SUPERADMIN,
    IsCustomerOrAbove,
    IsManagerOrAbove,
    get_user_role,
)
from .models import BankAccount, Transaction
from .serializers import (
    FUNDING_SOURCE_LABELS,
    WITHDRAWAL_METHOD_LABELS,
    AccountLookupSerializer,
    BankAccountSerializer,
    BankAccountUpdateSerializer,
    CustomerDetail360Serializer,
    CustomerListSerializer,
    DepositSerializer,
    StaffAccountUpdateSerializer,
    StaffDashboardSummarySerializer,
    TellerOperationSerializer,
    TransactionSerializer,
    TransferSerializer,
    WithdrawSerializer,
)

logger = logging.getLogger('finchat.banking')


def _get_user_account(user, lock: bool = False) -> BankAccount:
    qs = BankAccount.objects.select_related('user')
    if lock:
        qs = qs.select_for_update(of=('self',))
    try:
        return qs.get(user=user)
    except BankAccount.DoesNotExist as exc:
        raise NotFound('No bank account is associated with this user.') from exc


class MyBankAccountView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]

    @extend_schema(responses=BankAccountSerializer)
    def get(self, request):
        account = _get_user_account(request.user)
        return Response(BankAccountSerializer(account).data)

    @extend_schema(request=BankAccountUpdateSerializer, responses=BankAccountSerializer)
    def patch(self, request):
        account = _get_user_account(request.user)
        if not account.is_active:
            raise ValidationError('This bank account is currently frozen.')
        old_type = account.account_type
        serializer = BankAccountUpdateSerializer(account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if old_type != account.account_type:
            record_activity(
                request=request,
                actor=request.user,
                subject_user=request.user,
                category=ActivityLog.Category.BANKING,
                action='ACCOUNT_TYPE_CHANGED',
                description=f'Changed account {account.account_number} type from {old_type} to {account.account_type}',
                metadata={
                    'account_number': account.account_number,
                    'old_type': old_type,
                    'new_type': account.account_type,
                },
            )
        logger.info(
            'Account type updated',
            extra={
                'user_id': request.user.id,
                'account_number': account.account_number,
                'account_type': account.account_type,
            },
        )
        return Response(BankAccountSerializer(account).data)


class DepositView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]

    @extend_schema(request=DepositSerializer, responses=TransactionSerializer)
    @transaction.atomic
    def post(self, request):
        serializer = DepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']
        funding_source = serializer.validated_data.get('funding_source', 'bank_transfer')
        default_desc = FUNDING_SOURCE_LABELS.get(funding_source, 'Account Deposit')
        description = (serializer.validated_data['description'] or '').strip() or default_desc

        account = _get_user_account(request.user, lock=True)
        if not account.user.is_active or not account.is_active:
            raise ValidationError('This bank account is currently frozen or inactive.')

        channel = (
            Transaction.Channel.ATM if funding_source == 'atm_cash' else Transaction.Channel.ONLINE
        )

        account.balance += amount
        account.save(update_fields=['balance', 'updated_at'])

        txn = Transaction.objects.create(
            account=account,
            performed_by=request.user,
            transaction_type=Transaction.Type.DEPOSIT,
            channel=channel,
            amount=amount,
            balance_after=account.balance,
            description=description,
        )
        record_activity(
            request=request,
            actor=request.user,
            subject_user=request.user,
            category=ActivityLog.Category.BANKING,
            action='DEPOSIT',
            description=f'Self-service deposit of ${amount} via {funding_source} ({txn.reference})',
            metadata={
                'amount': str(amount),
                'balance_after': str(account.balance),
                'channel': channel,
                'funding_source': funding_source,
                'reference': txn.reference,
            },
        )
        logger.info(
            'Deposit completed',
            extra={
                'user_id': request.user.id,
                'account_number': account.account_number,
                'amount': str(amount),
                'channel': channel,
                'balance_after': str(account.balance),
                'reference': txn.reference,
            },
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)


class WithdrawView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]

    @extend_schema(request=WithdrawSerializer, responses=TransactionSerializer)
    @transaction.atomic
    def post(self, request):
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']
        withdrawal_method = serializer.validated_data.get('withdrawal_method', 'atm_cash')
        default_desc = WITHDRAWAL_METHOD_LABELS.get(withdrawal_method, 'Account Withdrawal')
        description = (serializer.validated_data['description'] or '').strip() or default_desc

        account = _get_user_account(request.user, lock=True)
        if not account.user.is_active or not account.is_active:
            raise ValidationError('This bank account is currently frozen or inactive.')
        if account.balance < amount:
            raise ValidationError('Insufficient funds for this withdrawal.')

        channel = (
            Transaction.Channel.ATM if withdrawal_method == 'atm_cash' else Transaction.Channel.ONLINE
        )

        account.balance -= amount
        account.save(update_fields=['balance', 'updated_at'])

        txn = Transaction.objects.create(
            account=account,
            performed_by=request.user,
            transaction_type=Transaction.Type.WITHDRAWAL,
            channel=channel,
            amount=amount,
            balance_after=account.balance,
            description=description,
        )
        record_activity(
            request=request,
            actor=request.user,
            subject_user=request.user,
            category=ActivityLog.Category.BANKING,
            action='WITHDRAWAL',
            description=f'Self-service withdrawal of ${amount} via {withdrawal_method} ({txn.reference})',
            metadata={
                'amount': str(amount),
                'balance_after': str(account.balance),
                'channel': channel,
                'withdrawal_method': withdrawal_method,
                'reference': txn.reference,
            },
        )
        logger.info(
            'Withdrawal completed',
            extra={
                'user_id': request.user.id,
                'account_number': account.account_number,
                'amount': str(amount),
                'channel': channel,
                'balance_after': str(account.balance),
                'reference': txn.reference,
            },
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)


class TransferView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]

    @extend_schema(request=TransferSerializer, responses=TransactionSerializer)
    @transaction.atomic
    def post(self, request):
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        to_account_number = serializer.validated_data['to_account_number']
        amount = serializer.validated_data['amount']
        description = serializer.validated_data['description']

        sender_preview = _get_user_account(request.user, lock=False)
        if sender_preview.account_number == to_account_number:
            raise ValidationError('Cannot transfer funds to the same account.')

        try:
            recipient_preview = BankAccount.objects.get(account_number=to_account_number)
        except BankAccount.DoesNotExist as exc:
            raise NotFound('Recipient bank account not found.') from exc

        locked_accounts = {
            acc.id: acc
            for acc in BankAccount.objects.select_for_update(of=('self',))
            .select_related('user')
            .filter(id__in=[sender_preview.id, recipient_preview.id])
            .order_by('id')
        }
        sender = locked_accounts[sender_preview.id]
        recipient = locked_accounts[recipient_preview.id]

        if not sender.user.is_active or not sender.is_active:
            raise ValidationError('Your bank account is frozen or inactive.')
        if not recipient.user.is_active or not recipient.is_active:
            raise ValidationError('Recipient bank account is frozen or inactive.')
        if sender.balance < amount:
            raise ValidationError('Insufficient funds for this transfer.')

        sender.balance -= amount
        recipient.balance += amount
        sender.save(update_fields=['balance', 'updated_at'])
        recipient.save(update_fields=['balance', 'updated_at'])

        base_ref = uuid.uuid4().hex[:10].upper()
        out_desc = description or f'Transfer to {recipient.account_number}'
        in_desc = description or f'Transfer from {sender.account_number}'

        txn_out = Transaction.objects.create(
            account=sender,
            related_account=recipient,
            performed_by=request.user,
            transaction_type=Transaction.Type.TRANSFER_OUT,
            channel=Transaction.Channel.ONLINE,
            amount=amount,
            balance_after=sender.balance,
            reference=f'TXN-{base_ref}-OUT',
            description=out_desc,
        )
        txn_in = Transaction.objects.create(
            account=recipient,
            related_account=sender,
            performed_by=request.user,
            transaction_type=Transaction.Type.TRANSFER_IN,
            channel=Transaction.Channel.ONLINE,
            amount=amount,
            balance_after=recipient.balance,
            reference=f'TXN-{base_ref}-IN',
            description=in_desc,
        )
        record_activity(
            request=request,
            actor=request.user,
            subject_user=sender.user,
            category=ActivityLog.Category.BANKING,
            action='TRANSFER_SENT',
            description=f'Transferred ${amount} to {recipient.account_number} ({recipient.user.username})',
            metadata={
                'amount': str(amount),
                'to_account': recipient.account_number,
                'reference': txn_out.reference,
            },
        )
        record_activity(
            request=request,
            actor=request.user,
            subject_user=recipient.user,
            category=ActivityLog.Category.BANKING,
            action='TRANSFER_RECEIVED',
            description=f'Received ${amount} from {sender.account_number} ({sender.user.username})',
            metadata={
                'amount': str(amount),
                'from_account': sender.account_number,
                'reference': txn_in.reference,
            },
        )
        logger.info(
            'Transfer completed',
            extra={
                'user_id': request.user.id,
                'from_account': sender.account_number,
                'to_account': recipient.account_number,
                'amount': str(amount),
                'reference': txn_out.reference,
            },
        )
        return Response(TransactionSerializer(txn_out).data, status=status.HTTP_201_CREATED)


class AccountLookupView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]

    @extend_schema(responses=AccountLookupSerializer(many=True))
    def get(self, request):
        query = request.query_params.get('q', '').strip()
        qs = (
            BankAccount.objects.select_related('user')
            .filter(is_active=True, user__is_active=True)
            .exclude(user=request.user)
        )
        if query:
            qs = qs.filter(
                Q(account_number__icontains=query)
                | Q(user__username__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
            )
        return Response(AccountLookupSerializer(qs[:20], many=True).data)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]
    filterset_fields = ['transaction_type', 'channel', 'account__account_number']
    search_fields = [
        'reference',
        'description',
        'account__account_number',
        'account__user__username',
        'account__user__first_name',
        'account__user__last_name',
        'performed_by__username',
    ]
    ordering_fields = ['created_at', 'amount']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Transaction.objects.none()
        user = self.request.user
        role_name = get_user_role(user)
        qs = Transaction.objects.select_related(
            'account',
            'account__user',
            'related_account',
            'related_account__user',
            'performed_by',
        )
        scope = self.request.query_params.get('scope')
        user_id = self.request.query_params.get('user_id')

        if role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER):
            if scope == 'mine':
                return qs.filter(account__user=user)
            if user_id:
                return qs.filter(account__user_id=user_id)
            if scope == 'all':
                return qs
            if not BankAccount.objects.filter(user=user).exists():
                return qs
        return qs.filter(account__user=user)


class StaffDashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrAbove]

    @extend_schema(responses=StaffDashboardSummarySerializer)
    def get(self, request):
        account_holders_qs = CustomUser.objects.filter(
            Q(role__name=ROLE_CUSTOMER) | Q(bank_account__isnull=False)
        ).distinct()
        accounts_agg = BankAccount.objects.aggregate(
            total_liquidity=Coalesce(Sum('balance'), Decimal('0.00')),
        )
        recent_txns = Transaction.objects.select_related(
            'account',
            'account__user',
            'related_account',
            'related_account__user',
            'performed_by',
        )[:8]
        recent_activities = ActivityLog.objects.select_related(
            'actor', 'actor__role', 'subject_user'
        )[:10]

        payload = {
            'total_customers': account_holders_qs.count(),
            'total_bank_accounts': BankAccount.objects.count(),
            'active_accounts': BankAccount.objects.filter(is_active=True).count(),
            'frozen_accounts': BankAccount.objects.filter(is_active=False).count(),
            'usd_endorsed_accounts': BankAccount.objects.filter(is_usd_endorsed=True).count(),
            'total_liquidity': accounts_agg['total_liquidity'],
            'total_transactions': Transaction.objects.count(),
            'pending_cheques': ChequeBookRequest.objects.filter(
                status=ChequeBookRequest.Status.PENDING
            ).count(),
            'pending_endorsements': Endorsement.objects.filter(
                status=Endorsement.Status.PENDING
            ).count(),
            'recent_transactions': TransactionSerializer(recent_txns, many=True).data,
            'recent_activities': recent_activities,
        }
        serializer = StaffDashboardSummarySerializer(payload)
        return Response(serializer.data)


class CustomerListView(generics.ListAPIView):
    serializer_class = CustomerListSerializer
    permission_classes = [IsAuthenticated, IsManagerOrAbove]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'username',
        'email',
        'first_name',
        'last_name',
        'phone',
        'bank_account__account_number',
    ]
    ordering_fields = ['created_at', 'username', 'bank_account__balance']

    @extend_schema(
        parameters=[
            OpenApiParameter('account_type', OpenApiTypes.STR, required=False),
            OpenApiParameter('account_active', OpenApiTypes.BOOL, required=False),
            OpenApiParameter('is_usd_endorsed', OpenApiTypes.BOOL, required=False),
            OpenApiParameter('role', OpenApiTypes.STR, required=False),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return CustomUser.objects.none()

        qs = (
            CustomUser.objects.select_related('role', 'bank_account', 'bank_account__user')
            .filter(Q(role__name=ROLE_CUSTOMER) | Q(bank_account__isnull=False))
            .annotate(
                transaction_count=Count('bank_account__transactions', distinct=True),
                pending_cheques=Count(
                    'cheque_requests',
                    filter=Q(cheque_requests__status=ChequeBookRequest.Status.PENDING),
                    distinct=True,
                ),
                pending_endorsements=Count(
                    'endorsements_made',
                    filter=Q(endorsements_made__status=Endorsement.Status.PENDING),
                    distinct=True,
                ),
                addresses_count=Count('addresses', distinct=True),
            )
            .distinct()
        )

        account_type = self.request.query_params.get('account_type')
        account_active = self.request.query_params.get('account_active')
        is_usd_endorsed = self.request.query_params.get('is_usd_endorsed')
        role_filter = self.request.query_params.get('role')

        if account_type:
            qs = qs.filter(bank_account__account_type=account_type)
        if account_active in ('true', 'false'):
            qs = qs.filter(bank_account__is_active=(account_active == 'true'))
        if is_usd_endorsed in ('true', 'false'):
            qs = qs.filter(bank_account__is_usd_endorsed=(is_usd_endorsed == 'true'))
        if role_filter:
            qs = qs.filter(role__name=role_filter)

        return qs


class CustomerDetailView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrAbove]

    @extend_schema(responses=CustomerDetail360Serializer)
    def get(self, request, user_id: int):
        try:
            target_user = (
                CustomUser.objects.select_related('role', 'profile', 'bank_account')
                .filter(Q(role__name=ROLE_CUSTOMER) | Q(bank_account__isnull=False))
                .get(pk=user_id)
            )
        except CustomUser.DoesNotExist as exc:
            raise NotFound('Customer or account holder not found.') from exc

        account = getattr(target_user, 'bank_account', None)
        txns_qs = Transaction.objects.filter(account=account) if account else Transaction.objects.none()
        txn_agg = txns_qs.aggregate(
            total_deposits=Coalesce(
                Sum('amount', filter=Q(transaction_type=Transaction.Type.DEPOSIT)), Decimal('0.00')
            ),
            total_withdrawals=Coalesce(
                Sum('amount', filter=Q(transaction_type=Transaction.Type.WITHDRAWAL)), Decimal('0.00')
            ),
            total_transfers_in=Coalesce(
                Sum('amount', filter=Q(transaction_type=Transaction.Type.TRANSFER_IN)), Decimal('0.00')
            ),
            total_transfers_out=Coalesce(
                Sum('amount', filter=Q(transaction_type=Transaction.Type.TRANSFER_OUT)), Decimal('0.00')
            ),
            transaction_count=Count('id'),
            last_transaction_at=Max('created_at'),
        )
        act_agg = ActivityLog.objects.filter(subject_user=target_user).aggregate(
            activity_count=Count('id'),
            last_activity_at=Max('created_at'),
        )

        stats = {
            **txn_agg,
            'pending_cheques': ChequeBookRequest.objects.filter(
                user=target_user, status=ChequeBookRequest.Status.PENDING
            ).count(),
            'pending_endorsements': Endorsement.objects.filter(
                requester=target_user, status=Endorsement.Status.PENDING
            ).count(),
            'activity_count': act_agg['activity_count'],
            'last_activity_at': act_agg['last_activity_at'],
        }

        addresses = Address.objects.filter(user=target_user)
        serializer = CustomerDetail360Serializer(
            {
                'user': target_user,
                'bank_account': account,
                'addresses': addresses,
                'stats': stats,
            }
        )
        return Response(serializer.data)


class CustomerAccountManageView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrAbove]

    @extend_schema(request=StaffAccountUpdateSerializer, responses=BankAccountSerializer)
    @transaction.atomic
    def patch(self, request, user_id: int):
        if user_id == request.user.id:
            raise ValidationError(
                'Separation of Duties: You cannot alter your own bank account status or settings from the staff portal.'
            )

        try:
            account = (
                BankAccount.objects.select_for_update(of=('self',))
                .select_related('user')
                .get(user_id=user_id)
            )
        except BankAccount.DoesNotExist as exc:
            raise NotFound('Bank account not found for this user.') from exc

        serializer = StaffAccountUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reason = (data.get('reason') or '').strip()

        updated_fields = ['updated_at']
        if 'account_type' in data and data['account_type'] != account.account_type:
            old_type = account.account_type
            account.account_type = data['account_type']
            updated_fields.append('account_type')
            record_activity(
                request=request,
                actor=request.user,
                subject_user=account.user,
                category=ActivityLog.Category.BANKING,
                action='ACCOUNT_TYPE_CHANGED',
                description=(
                    f'Staff {request.user.username} changed {account.account_number} '
                    f'type from {old_type} to {account.account_type}'
                    + (f' ({reason})' if reason else '')
                ),
                metadata={
                    'account_number': account.account_number,
                    'old_type': old_type,
                    'new_type': account.account_type,
                    'reason': reason,
                },
            )

        if 'is_active' in data and data['is_active'] != account.is_active:
            account.is_active = data['is_active']
            updated_fields.append('is_active')
            action_name = 'ACCOUNT_UNFROZEN' if account.is_active else 'ACCOUNT_FROZEN'
            state_label = 'unfrozen / activated' if account.is_active else 'frozen / suspended'
            record_activity(
                request=request,
                actor=request.user,
                subject_user=account.user,
                category=ActivityLog.Category.BANKING,
                action=action_name,
                description=(
                    f'Staff {request.user.username} marked account {account.account_number} as {state_label}'
                    + (f' — {reason}' if reason else '')
                ),
                metadata={
                    'account_number': account.account_number,
                    'is_active': account.is_active,
                    'reason': reason,
                },
            )

        if len(updated_fields) > 1:
            account.save(update_fields=updated_fields)
        logger.info(
            'Staff updated customer bank account',
            extra={
                'staff_user_id': request.user.id,
                'target_user_id': user_id,
                'account_number': account.account_number,
                'is_active': account.is_active,
                'account_type': account.account_type,
            },
        )
        return Response(BankAccountSerializer(account).data)


class TellerDepositView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrAbove]

    @extend_schema(request=TellerOperationSerializer, responses=TransactionSerializer)
    @transaction.atomic
    def post(self, request, user_id: int):
        if user_id == request.user.id:
            raise ValidationError(
                'Separation of Duties: Staff cannot perform branch teller deposits on their own personal bank account.'
            )

        serializer = TellerOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']
        description = (serializer.validated_data['description'] or '').strip() or (
            f'Branch teller cash deposit (processed by {request.user.username})'
        )

        try:
            account = (
                BankAccount.objects.select_for_update(of=('self',))
                .select_related('user')
                .get(user_id=user_id)
            )
        except BankAccount.DoesNotExist as exc:
            raise NotFound('Bank account not found for this customer.') from exc

        if not account.user.is_active or not account.is_active:
            raise ValidationError('This bank account is currently frozen or inactive.')

        account.balance += amount
        account.save(update_fields=['balance', 'updated_at'])

        txn = Transaction.objects.create(
            account=account,
            performed_by=request.user,
            transaction_type=Transaction.Type.DEPOSIT,
            channel=Transaction.Channel.BRANCH_TELLER,
            amount=amount,
            balance_after=account.balance,
            description=description,
        )
        record_activity(
            request=request,
            actor=request.user,
            subject_user=account.user,
            category=ActivityLog.Category.BANKING,
            action='TELLER_DEPOSIT',
            description=(
                f'Teller {request.user.username} deposited ${amount} into '
                f'{account.account_number} ({txn.reference})'
            ),
            metadata={
                'amount': str(amount),
                'balance_after': str(account.balance),
                'channel': Transaction.Channel.BRANCH_TELLER,
                'reference': txn.reference,
            },
        )
        logger.info(
            'Branch teller deposit completed',
            extra={
                'staff_user_id': request.user.id,
                'target_user_id': user_id,
                'account_number': account.account_number,
                'amount': str(amount),
                'reference': txn.reference,
            },
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)


class TellerWithdrawView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrAbove]

    @extend_schema(request=TellerOperationSerializer, responses=TransactionSerializer)
    @transaction.atomic
    def post(self, request, user_id: int):
        if user_id == request.user.id:
            raise ValidationError(
                'Separation of Duties: Staff cannot perform branch teller withdrawals on their own personal bank account.'
            )

        serializer = TellerOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']
        description = (serializer.validated_data['description'] or '').strip() or (
            f'Branch teller cash withdrawal (processed by {request.user.username})'
        )

        try:
            account = (
                BankAccount.objects.select_for_update(of=('self',))
                .select_related('user')
                .get(user_id=user_id)
            )
        except BankAccount.DoesNotExist as exc:
            raise NotFound('Bank account not found for this customer.') from exc

        if not account.user.is_active or not account.is_active:
            raise ValidationError('This bank account is currently frozen or inactive.')
        if account.balance < amount:
            raise ValidationError('Insufficient customer balance for this teller withdrawal.')

        account.balance -= amount
        account.save(update_fields=['balance', 'updated_at'])

        txn = Transaction.objects.create(
            account=account,
            performed_by=request.user,
            transaction_type=Transaction.Type.WITHDRAWAL,
            channel=Transaction.Channel.BRANCH_TELLER,
            amount=amount,
            balance_after=account.balance,
            description=description,
        )
        record_activity(
            request=request,
            actor=request.user,
            subject_user=account.user,
            category=ActivityLog.Category.BANKING,
            action='TELLER_WITHDRAWAL',
            description=(
                f'Teller {request.user.username} withdrew ${amount} from '
                f'{account.account_number} ({txn.reference})'
            ),
            metadata={
                'amount': str(amount),
                'balance_after': str(account.balance),
                'channel': Transaction.Channel.BRANCH_TELLER,
                'reference': txn.reference,
            },
        )
        logger.info(
            'Branch teller withdrawal completed',
            extra={
                'staff_user_id': request.user.id,
                'target_user_id': user_id,
                'account_number': account.account_number,
                'amount': str(amount),
                'reference': txn.reference,
            },
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)
