import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.audit import record_activity
from apps.accounts.models import ActivityLog, Address
from core.internal_auth import HasInternalAPIKey, get_internal_user
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

