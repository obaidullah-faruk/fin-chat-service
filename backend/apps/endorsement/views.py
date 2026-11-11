import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.audit import record_activity
from apps.accounts.models import ActivityLog
from apps.banking.models import BankAccount
from core.permissions import (
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SUPERADMIN,
    IsCustomerOrAbove,
    IsManagerOrAbove,
    get_user_role,
)
from .models import Endorsement
from .serializers import (
    EndorsementCreateSerializer,
    EndorsementReviewSerializer,
    EndorsementSerializer,
)

logger = logging.getLogger('finchat.endorsement')


class EndorsementListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]
    filterset_fields = ['status', 'endorsement_type']
    search_fields = ['requester__username', 'passport_number', 'notes']
    ordering_fields = ['created_at', 'amount']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return EndorsementCreateSerializer
        return EndorsementSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Endorsement.objects.none()
        user = self.request.user
        role_name = get_user_role(user)
        qs = Endorsement.objects.select_related('requester', 'requester__bank_account', 'endorser')
        mine = self.request.query_params.get('mine')
        user_id = self.request.query_params.get('user_id')
        if role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER) and mine != 'true':
            if user_id:
                return qs.filter(requester_id=user_id)
            return qs
        return qs.filter(requester=user)

    @extend_schema(request=EndorsementCreateSerializer, responses=EndorsementSerializer)
    def post(self, request, *args, **kwargs):
        serializer = EndorsementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endorsement = Endorsement.objects.create(
            requester=request.user,
            currency='USD',
            **serializer.validated_data,
        )
        record_activity(
            request=request,
            actor=request.user,
            subject_user=request.user,
            category=ActivityLog.Category.ENDORSEMENT,
            action='ENDORSEMENT_REQUESTED',
            description=(
                f'Submitted USD endorsement request #{endorsement.id} ({endorsement.endorsement_type})'
            ),
            metadata={
                'endorsement_id': endorsement.id,
                'endorsement_type': endorsement.endorsement_type,
                'amount': str(endorsement.amount) if endorsement.amount else None,
            },
        )
        logger.info(
            'USD endorsement requested',
            extra={
                'user_id': request.user.id,
                'endorsement_id': endorsement.id,
                'endorsement_type': endorsement.endorsement_type,
                'amount': str(endorsement.amount) if endorsement.amount else None,
            },
        )
        return Response(EndorsementSerializer(endorsement).data, status=status.HTTP_201_CREATED)


class EndorsementReviewView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrAbove]

    @extend_schema(request=EndorsementReviewSerializer, responses=EndorsementSerializer)
    @transaction.atomic
    def patch(self, request, pk: int):
        try:
            endorsement = Endorsement.objects.select_for_update(of=('self',)).select_related(
                'requester', 'endorser'
            ).get(pk=pk)
        except Endorsement.DoesNotExist:
            return Response(
                {'detail': 'Endorsement request not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if endorsement.requester_id == request.user.id:
            raise ValidationError(
                'Separation of Duties: You cannot approve or reject your own USD endorsement request.'
            )

        if endorsement.status != Endorsement.Status.PENDING:
            raise ValidationError(
                f'Endorsement request is already {endorsement.status} and cannot be modified.'
            )

        serializer = EndorsementReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_status = serializer.validated_data['status']
        review_remarks = serializer.validated_data['review_remarks']

        endorsement.status = next_status
        endorsement.endorser = request.user
        endorsement.review_remarks = review_remarks
        endorsement.reviewed_at = timezone.now()
        endorsement.save()

        if next_status == Endorsement.Status.APPROVED:
            account = BankAccount.objects.select_for_update().filter(
                user=endorsement.requester
            ).first()
            if account:
                account.is_usd_endorsed = True
                if endorsement.amount is not None:
                    account.usd_endorsement_limit = endorsement.amount
                elif account.usd_endorsement_limit == Decimal('0.00'):
                    account.usd_endorsement_limit = Decimal('5000.00')
                account.save(update_fields=['is_usd_endorsed', 'usd_endorsement_limit', 'updated_at'])

        record_activity(
            request=request,
            actor=request.user,
            subject_user=endorsement.requester,
            category=ActivityLog.Category.ENDORSEMENT,
            action='ENDORSEMENT_REVIEWED',
            description=(
                f'{request.user.username} {endorsement.status} USD endorsement #{endorsement.id}'
            ),
            metadata={
                'endorsement_id': endorsement.id,
                'status': endorsement.status,
                'amount': str(endorsement.amount) if endorsement.amount else None,
            },
        )
        logger.info(
            'USD endorsement reviewed',
            extra={
                'endorsement_id': endorsement.id,
                'status': endorsement.status,
                'reviewed_by': request.user.id,
            },
        )
        return Response(EndorsementSerializer(endorsement).data)

