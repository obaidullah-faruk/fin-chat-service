import logging
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.internal_auth import HasInternalAPIKey, get_internal_user
from .models import Transaction
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

