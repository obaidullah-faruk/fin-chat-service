import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.audit import record_activity
from apps.accounts.models import ActivityLog, Address
from apps.endorsement.models import Endorsement
from core.internal_auth import HasInternalAPIKey, get_internal_user
from core.permissions import ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERADMIN
from .models import ChequeBookRequest
from .serializers import ChequeBookRequestSerializer, InternalChequeRequestCreateSerializer
from .views import _format_address

logger = logging.getLogger('finchat.cheque.internal')


class InternalChequeRequestCreateView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalAPIKey]

    @extend_schema(
        tags=['Internal Service'],
        request=InternalChequeRequestCreateSerializer,
        responses={201: ChequeBookRequestSerializer},
    )
    def post(self, request):
        user = get_internal_user(request)
        serializer = InternalChequeRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        delivery_address_id = serializer.validated_data.get('delivery_address_id')
        if delivery_address_id is not None:
            try:
                delivery_address = Address.objects.get(pk=delivery_address_id, user=user)
            except Address.DoesNotExist as exc:
                raise NotFound('Delivery address not found for this user.') from exc
        else:
            delivery_address = Address.objects.filter(user=user, is_primary=True).first()

        snapshot = _format_address(delivery_address) if delivery_address else ''
        req_obj = ChequeBookRequest.objects.create(
            user=user,
            leaves_requested=serializer.validated_data['leaves_requested'],
            delivery_address=delivery_address,
            delivery_address_snapshot=snapshot,
            remarks=serializer.validated_data['remarks'],
        )
        record_activity(
            request=request,
            actor=user,
            subject_user=user,
            category=ActivityLog.Category.CHEQUE,
            action='CHEQUE_REQUESTED',
            description=f'Requested {req_obj.leaves_requested}-leaf cheque book (#{req_obj.id}) via assistant',
            metadata={
                'cheque_request_id': req_obj.id,
                'leaves': req_obj.leaves_requested,
                'source': 'internal_service',
            },
        )
        logger.info(
            'Internal cheque book requested',
            extra={
                'user_id': user.id,
                'cheque_request_id': req_obj.id,
                'leaves_requested': req_obj.leaves_requested,
            },
        )
        return Response(ChequeBookRequestSerializer(req_obj).data, status=status.HTTP_201_CREATED)


class InternalPendingReviewsView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalAPIKey]

    @extend_schema(
        tags=['Internal Service'],
        parameters=[
            OpenApiParameter('type', str, required=False, description='all, cheque, or endorsement'),
        ],
    )
    def get(self, request):
        user = get_internal_user(request)
        role_name = getattr(user.role, 'name', '') if user.role else 'customer'
        is_staff = role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER)
        if not is_staff:
            raise PermissionDenied('Staff privileges required for viewing pending review items.')

        review_type = request.query_params.get('type', 'all').strip().lower()

        pending_cheques_data = []
        if review_type in ('all', 'cheque'):
            cheques = ChequeBookRequest.objects.select_related('user').filter(
                status=ChequeBookRequest.Status.PENDING
            )
            for c in cheques:
                pending_cheques_data.append(
                    {
                        'id': c.id,
                        'user_id': c.user_id,
                        'username': c.user.username,
                        'full_name': c.user.full_name,
                        'leaves_requested': c.leaves_requested,
                        'status': c.status,
                        'remarks': c.remarks,
                        'requested_at': c.requested_at.isoformat(),
                    }
                )

        pending_endorsements_data = []
        if review_type in ('all', 'endorsement'):
            endorsements = Endorsement.objects.select_related('requester').filter(
                status=Endorsement.Status.PENDING
            )
            for e in endorsements:
                pending_endorsements_data.append(
                    {
                        'id': e.id,
                        'user_id': e.requester_id,
                        'username': e.requester.username,
                        'full_name': e.requester.full_name,
                        'amount': str(e.amount) if e.amount else None,
                        'endorsement_type': e.endorsement_type,
                        'status': e.status,
                        'notes': e.notes,
                        'created_at': e.created_at.isoformat(),
                    }
                )

        logger.info(
            'Internal pending reviews queried',
            extra={
                'user_id': user.id,
                'role': role_name,
                'cheques_count': len(pending_cheques_data),
                'endorsements_count': len(pending_endorsements_data),
            },
        )
        return Response(
            {
                'pending_cheques_count': len(pending_cheques_data),
                'pending_endorsements_count': len(pending_endorsements_data),
                'pending_cheques': pending_cheques_data,
                'pending_endorsements': pending_endorsements_data,
            }
        )

