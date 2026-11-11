import logging
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.audit import record_activity
from apps.accounts.models import ActivityLog, Address
from core.permissions import (
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SUPERADMIN,
    IsCustomerOrAbove,
    IsManagerOrAbove,
    get_user_role,
)
from .models import ChequeBookRequest
from .serializers import (
    ChequeBookCreateSerializer,
    ChequeBookRequestSerializer,
    ChequeBookReviewSerializer,
)

logger = logging.getLogger('finchat.cheque')


def _format_address(addr: Address) -> str:
    return f'{addr.label.title()}: {addr.street}, {addr.city}, {addr.state} {addr.postal_code}, {addr.country}'


class ChequeBookRequestCreateView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]

    @extend_schema(request=ChequeBookCreateSerializer, responses=ChequeBookRequestSerializer)
    def post(self, request):
        serializer = ChequeBookCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        delivery_address = serializer.validated_data.get('delivery_address')
        if delivery_address is None:
            delivery_address = Address.objects.filter(user=request.user, is_primary=True).first()

        snapshot = _format_address(delivery_address) if delivery_address else ''
        req_obj = ChequeBookRequest.objects.create(
            user=request.user,
            leaves_requested=serializer.validated_data['leaves_requested'],
            delivery_address=delivery_address,
            delivery_address_snapshot=snapshot,
            remarks=serializer.validated_data.get('remarks', ''),
        )
        record_activity(
            request=request,
            actor=request.user,
            subject_user=request.user,
            category=ActivityLog.Category.CHEQUE,
            action='CHEQUE_REQUESTED',
            description=f'Requested {req_obj.leaves_requested}-leaf cheque book (#{req_obj.id})',
            metadata={'cheque_request_id': req_obj.id, 'leaves': req_obj.leaves_requested},
        )
        logger.info(
            'Cheque book requested',
            extra={
                'user_id': request.user.id,
                'cheque_request_id': req_obj.id,
                'leaves_requested': req_obj.leaves_requested,
            },
        )
        return Response(ChequeBookRequestSerializer(req_obj).data, status=status.HTTP_201_CREATED)


class ChequeBookRequestListView(generics.ListAPIView):
    serializer_class = ChequeBookRequestSerializer
    permission_classes = [IsAuthenticated, IsCustomerOrAbove]
    filterset_fields = ['status']
    search_fields = ['user__username', 'remarks']
    ordering_fields = ['requested_at', 'reviewed_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ChequeBookRequest.objects.none()
        user = self.request.user
        role_name = get_user_role(user)
        qs = ChequeBookRequest.objects.select_related('user', 'user__bank_account', 'reviewed_by')
        mine = self.request.query_params.get('mine')
        user_id = self.request.query_params.get('user_id')
        if role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER) and mine != 'true':
            if user_id:
                return qs.filter(user_id=user_id)
            return qs
        return qs.filter(user=user)


class ChequeBookReviewView(APIView):
    permission_classes = [IsAuthenticated, IsManagerOrAbove]

    @extend_schema(request=ChequeBookReviewSerializer, responses=ChequeBookRequestSerializer)
    def patch(self, request, pk: int):
        try:
            cheque_req = ChequeBookRequest.objects.select_related('user', 'reviewed_by').get(pk=pk)
        except ChequeBookRequest.DoesNotExist:
            return Response(
                {'detail': 'Cheque book request not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if cheque_req.user_id == request.user.id:
            raise ValidationError(
                'Separation of Duties: You cannot approve, reject, or issue your own cheque book request.'
            )

        serializer = ChequeBookReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_status = serializer.validated_data['status']
        remarks = serializer.validated_data['remarks']

        valid_transitions = {
            ChequeBookRequest.Status.PENDING: (
                ChequeBookRequest.Status.APPROVED,
                ChequeBookRequest.Status.REJECTED,
            ),
            ChequeBookRequest.Status.APPROVED: (ChequeBookRequest.Status.ISSUED,),
        }
        allowed_next = valid_transitions.get(cheque_req.status, ())
        if next_status not in allowed_next:
            raise ValidationError(
                f'Cannot transition cheque request from {cheque_req.status} to {next_status}.'
            )

        cheque_req.status = next_status
        cheque_req.reviewed_by = request.user
        cheque_req.reviewed_at = timezone.now()
        if remarks:
            cheque_req.remarks = remarks
        cheque_req.save()

        record_activity(
            request=request,
            actor=request.user,
            subject_user=cheque_req.user,
            category=ActivityLog.Category.CHEQUE,
            action='CHEQUE_REVIEWED',
            description=(
                f'{request.user.username} marked cheque book request #{cheque_req.id} '
                f'as {cheque_req.status}'
            ),
            metadata={'cheque_request_id': cheque_req.id, 'status': cheque_req.status},
        )
        logger.info(
            'Cheque book request reviewed',
            extra={
                'cheque_request_id': cheque_req.id,
                'status': cheque_req.status,
                'reviewed_by': request.user.id,
            },
        )
        return Response(ChequeBookRequestSerializer(cheque_req).data)

