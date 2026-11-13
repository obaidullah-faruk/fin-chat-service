import logging
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import CustomUser
from apps.cheque.models import ChequeBookRequest
from apps.endorsement.models import Endorsement
from core.internal_auth import HasInternalAPIKey, get_internal_user
from core.permissions import ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERADMIN
from .models import BankAccount, Transaction
from .serializers import (
    InternalAccountInfoSerializer,
    InternalBalanceSerializer,
    InternalStatementResponseSerializer,
    InternalTransactionListResponseSerializer,
    TransactionSerializer,
)
from .views import _get_user_account

logger = logging.getLogger('finchat.banking.internal')

DEFAULT_TRANSACTIONS_LIMIT = 10
MAX_TRANSACTIONS_LIMIT = 100


class _BaseInternalBankingView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalAPIKey]


class InternalBalanceView(_BaseInternalBankingView):
    @extend_schema(
        tags=['Internal Banking'],
        responses=InternalBalanceSerializer,
    )
    def get(self, request):
        user = get_internal_user(request)
        account = _get_user_account(user)
        logger.info(
            'Internal balance queried',
            extra={'user_id': user.id, 'account_number': account.account_number},
        )
        return Response(InternalBalanceSerializer(account).data)


class InternalAccountInfoView(_BaseInternalBankingView):
    @extend_schema(
        tags=['Internal Banking'],
        responses=InternalAccountInfoSerializer,
    )
    def get(self, request):
        user = get_internal_user(request)
        account = _get_user_account(user)
        logger.info(
            'Internal account info queried',
            extra={'user_id': user.id, 'account_number': account.account_number},
        )
        return Response(InternalAccountInfoSerializer(account).data)


class InternalTransactionsView(_BaseInternalBankingView):
    @extend_schema(
        tags=['Internal Banking'],
        parameters=[
            OpenApiParameter('limit', OpenApiTypes.INT, required=False),
            OpenApiParameter(
                'transaction_type',
                OpenApiTypes.STR,
                required=False,
                enum=list(Transaction.Type.values),
            ),
        ],
        responses=InternalTransactionListResponseSerializer,
    )
    def get(self, request):
        user = get_internal_user(request)
        account = _get_user_account(user)

        raw_limit = request.query_params.get('limit')
        if raw_limit is not None and raw_limit != '':
            try:
                limit = int(raw_limit)
            except ValueError as exc:
                raise ValidationError({'detail': 'limit must be a positive integer.'}) from exc
            if limit <= 0:
                raise ValidationError({'detail': 'limit must be a positive integer.'})
            limit = min(limit, MAX_TRANSACTIONS_LIMIT)
        else:
            limit = DEFAULT_TRANSACTIONS_LIMIT

        qs = Transaction.objects.select_related(
            'account',
            'account__user',
            'related_account',
            'related_account__user',
            'performed_by',
        ).filter(account=account)

        transaction_type = request.query_params.get('transaction_type', '').strip()
        if transaction_type:
            if transaction_type not in Transaction.Type.values:
                allowed = ', '.join(Transaction.Type.values)
                raise ValidationError(
                    {'detail': f'Invalid transaction_type. Must be one of: {allowed}.'}
                )
            qs = qs.filter(transaction_type=transaction_type)

        txns = list(qs[:limit])
        logger.info(
            'Internal transactions queried',
            extra={
                'user_id': user.id,
                'account_number': account.account_number,
                'count': len(txns),
            },
        )
        return Response(
            {
                'account_number': account.account_number,
                'count': len(txns),
                'transactions': TransactionSerializer(txns, many=True).data,
            }
        )


class InternalStatementView(_BaseInternalBankingView):
    @extend_schema(
        tags=['Internal Banking'],
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, required=False),
            OpenApiParameter('end_date', OpenApiTypes.DATE, required=False),
        ],
        responses=InternalStatementResponseSerializer,
    )
    def get(self, request):
        user = get_internal_user(request)
        account = _get_user_account(user)

        raw_start = request.query_params.get('start_date', '').strip()
        raw_end = request.query_params.get('end_date', '').strip()

        start_date = None
        if raw_start:
            start_date = parse_date(raw_start)
            if start_date is None:
                raise ValidationError(
                    {'detail': 'Invalid start_date. Expected YYYY-MM-DD format.'}
                )

        end_date = None
        if raw_end:
            end_date = parse_date(raw_end)
            if end_date is None:
                raise ValidationError(
                    {'detail': 'Invalid end_date. Expected YYYY-MM-DD format.'}
                )

        if start_date and end_date and start_date > end_date:
            raise ValidationError({'detail': 'start_date cannot be after end_date.'})

        qs = Transaction.objects.select_related(
            'account',
            'account__user',
            'related_account',
            'related_account__user',
            'performed_by',
        ).filter(account=account)

        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        summary = qs.aggregate(
            total_deposits=Coalesce(
                Sum('amount', filter=Q(transaction_type=Transaction.Type.DEPOSIT)),
                Decimal('0.00'),
            ),
            total_withdrawals=Coalesce(
                Sum('amount', filter=Q(transaction_type=Transaction.Type.WITHDRAWAL)),
                Decimal('0.00'),
            ),
            total_transfers_in=Coalesce(
                Sum('amount', filter=Q(transaction_type=Transaction.Type.TRANSFER_IN)),
                Decimal('0.00'),
            ),
            total_transfers_out=Coalesce(
                Sum('amount', filter=Q(transaction_type=Transaction.Type.TRANSFER_OUT)),
                Decimal('0.00'),
            ),
            transaction_count=Count('id'),
        )

        txns = list(qs)
        logger.info(
            'Internal statement queried',
            extra={
                'user_id': user.id,
                'account_number': account.account_number,
                'transaction_count': summary['transaction_count'],
            },
        )
        return Response(
            {
                'account': InternalAccountInfoSerializer(account).data,
                'period': {
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None,
                },
                'summary': {
                    'total_deposits': str(summary['total_deposits']),
                    'total_withdrawals': str(summary['total_withdrawals']),
                    'total_transfers_in': str(summary['total_transfers_in']),
                    'total_transfers_out': str(summary['total_transfers_out']),
                    'transaction_count': summary['transaction_count'],
                },
                'transactions': TransactionSerializer(txns, many=True).data,
            }
        )


class InternalTransactionLookupView(_BaseInternalBankingView):
    @extend_schema(
        tags=['Internal Banking'],
        parameters=[
            OpenApiParameter('reference', OpenApiTypes.STR, required=True),
        ],
        responses=TransactionSerializer,
    )
    def get(self, request):
        user = get_internal_user(request)
        reference = request.query_params.get('reference', '').strip()
        if not reference:
            raise ValidationError({'detail': 'reference query parameter is required.'})

        try:
            txn = Transaction.objects.select_related(
                'account',
                'account__user',
                'related_account',
                'related_account__user',
                'performed_by',
            ).get(reference__iexact=reference)
        except Transaction.DoesNotExist as exc:
            raise NotFound(f"Transaction with reference '{reference}' not found.") from exc

        role_name = getattr(user.role, 'name', '') if user.role else 'customer'
        is_staff = role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER)

        if not is_staff:
            is_owner = (txn.account.user_id == user.id) or (
                txn.related_account and txn.related_account.user_id == user.id
            )
            if not is_owner:
                raise NotFound(f"Transaction with reference '{reference}' not found.")

        logger.info(
            'Internal transaction lookup executed',
            extra={'user_id': user.id, 'role': role_name, 'reference': reference},
        )
        return Response(TransactionSerializer(txn).data)


class InternalAccountLookupView(_BaseInternalBankingView):
    @extend_schema(
        tags=['Internal Banking'],
        parameters=[
            OpenApiParameter('query', OpenApiTypes.STR, required=False),
            OpenApiParameter('account_number', OpenApiTypes.STR, required=False),
        ],
    )
    def get(self, request):
        user = get_internal_user(request)
        raw_query = (
            request.query_params.get('query')
            or request.query_params.get('account_number')
            or ''
        ).strip()
        if not raw_query:
            raise ValidationError({'detail': 'query or account_number parameter is required.'})

        role_name = getattr(user.role, 'name', '') if user.role else 'customer'
        is_staff = role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER)

        qs = BankAccount.objects.select_related('user')
        if not is_staff:
            qs = qs.filter(is_active=True, user__is_active=True)

        account = qs.filter(
            Q(account_number__iexact=raw_query) | Q(user__username__iexact=raw_query)
        ).first()

        if not account:
            account = qs.filter(
                Q(account_number__icontains=raw_query)
                | Q(user__username__icontains=raw_query)
                | Q(user__first_name__icontains=raw_query)
                | Q(user__last_name__icontains=raw_query)
            ).first()

        if not account:
            raise NotFound(f"No bank account found matching '{raw_query}'.")

        logger.info(
            'Internal account lookup executed',
            extra={
                'user_id': user.id,
                'role': role_name,
                'query': raw_query,
                'target_account': account.account_number,
            },
        )

        if is_staff:
            return Response(
                {
                    'account_number': account.account_number,
                    'account_type': account.account_type,
                    'balance': str(account.balance),
                    'currency': account.currency,
                    'is_active': account.is_active,
                    'is_usd_endorsed': account.is_usd_endorsed,
                    'usd_endorsement_limit': str(account.usd_endorsement_limit),
                    'holder_username': account.user.username,
                    'holder_name': account.user.full_name,
                    'holder_email': account.user.email,
                    'created_at': account.created_at.isoformat(),
                }
            )

        # For retail customers: provide safe recipient confirmation
        return Response(
            {
                'account_number': account.account_number,
                'account_type': account.account_type,
                'holder_name': account.user.full_name,
                'is_active': account.is_active,
            }
        )


class InternalDashboardSummaryView(_BaseInternalBankingView):
    @extend_schema(
        tags=['Internal Banking'],
    )
    def get(self, request):
        user = get_internal_user(request)
        role_name = getattr(user.role, 'name', '') if user.role else 'customer'
        is_staff = role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER)
        if not is_staff:
            raise PermissionDenied('Administrative privileges required for dashboard summary.')

        account_holders_qs = CustomUser.objects.filter(
            Q(role__name='customer') | Q(bank_account__isnull=False)
        ).distinct()
        accounts_agg = BankAccount.objects.aggregate(
            total_liquidity=Coalesce(Sum('balance'), Decimal('0.00')),
        )

        data = {
            'total_customers': account_holders_qs.count(),
            'total_bank_accounts': BankAccount.objects.count(),
            'active_accounts': BankAccount.objects.filter(is_active=True).count(),
            'frozen_accounts': BankAccount.objects.filter(is_active=False).count(),
            'usd_endorsed_accounts': BankAccount.objects.filter(is_usd_endorsed=True).count(),
            'total_liquidity': str(accounts_agg['total_liquidity']),
            'total_transactions': Transaction.objects.count(),
            'pending_cheques': ChequeBookRequest.objects.filter(
                status=ChequeBookRequest.Status.PENDING
            ).count(),
            'pending_endorsements': Endorsement.objects.filter(
                status=Endorsement.Status.PENDING
            ).count(),
        }

        logger.info(
            'Internal dashboard summary queried',
            extra={'user_id': user.id, 'role': role_name},
        )
        return Response(data)

