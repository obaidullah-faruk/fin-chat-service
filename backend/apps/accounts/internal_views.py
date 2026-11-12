import logging

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.banking.models import BankAccount
from apps.endorsement.models import Endorsement
from core.internal_auth import HasInternalAPIKey, get_internal_user
from .audit import record_activity
from .models import ActivityLog, Address, UserProfile
from .serializers import (
    AddressSerializer,
    InternalAddressUpsertSerializer,
    InternalKYCStatusSerializer,
)

logger = logging.getLogger('finchat.accounts.internal')


class _BaseInternalServiceView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalAPIKey]


class InternalAddressUpdateView(_BaseInternalServiceView):
    @extend_schema(
        tags=['Internal Service'],
        request=InternalAddressUpsertSerializer,
        responses={200: AddressSerializer, 201: AddressSerializer},
    )
    @transaction.atomic
    def post(self, request):
        user = get_internal_user(request)
        serializer = InternalAddressUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        address_id = data.get('address_id')
        is_primary = data['is_primary']
        fields = {
            'label': data['label'],
            'street': data['street'].strip(),
            'city': data['city'].strip(),
            'state': data['state'].strip(),
            'postal_code': data['postal_code'].strip(),
            'country': data['country'].strip(),
            'is_primary': is_primary,
        }

        created = False
        if address_id is not None:
            try:
                address = Address.objects.get(pk=address_id, user=user)
            except Address.DoesNotExist as exc:
                raise NotFound('Address not found for this user.') from exc
            for key, value in fields.items():
                setattr(address, key, value)
            address.save()
        elif is_primary:
            address = Address.objects.filter(user=user, is_primary=True).first()
            if address is not None:
                for key, value in fields.items():
                    setattr(address, key, value)
                address.save()
            else:
                address = Address.objects.create(user=user, **fields)
                created = True
        else:
            address = Address.objects.create(user=user, **fields)
            created = True

        action = 'ADDRESS_CREATED' if created else 'ADDRESS_UPDATED'
        record_activity(
            request=request,
            actor=user,
            subject_user=user,
            category=ActivityLog.Category.PROFILE,
            action=action,
            description=(
                f'{"Added" if created else "Updated"} {address.label} address in '
                f'{address.city}, {address.country} via assistant'
            ),
            metadata={
                'address_id': address.id,
                'label': address.label,
                'source': 'internal_service',
            },
        )
        logger.info(
            'Internal address saved',
            extra={'user_id': user.id, 'address_id': address.id, 'is_created': created},
        )
        resp_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(AddressSerializer(address).data, status=resp_status)


class InternalKYCStatusView(_BaseInternalServiceView):
    @extend_schema(
        tags=['Internal Service'],
        responses=InternalKYCStatusSerializer,
    )
    def get(self, request):
        user = get_internal_user(request)
        profile = UserProfile.objects.filter(user=user).first()
        primary_address = Address.objects.filter(user=user, is_primary=True).first()
        account = BankAccount.objects.filter(user=user).first()
        latest_endorsement = (
            Endorsement.objects.filter(requester=user).order_by('-created_at').first()
        )

        has_national_id = bool(profile and profile.national_id.strip())
        has_date_of_birth = bool(profile and profile.date_of_birth)
        has_primary_address = primary_address is not None
        has_bank_account = account is not None
        is_usd_endorsed = bool(account and account.is_usd_endorsed)

        missing_fields = []
        if not has_national_id:
            missing_fields.append('national_id')
        if not has_date_of_birth:
            missing_fields.append('date_of_birth')
        if not has_primary_address:
            missing_fields.append('primary_address')

        if not missing_fields:
            kyc_status = 'verified'
        elif has_national_id or has_date_of_birth or has_primary_address or bool(user.phone.strip()):
            kyc_status = 'partial'
        else:
            kyc_status = 'incomplete'

        payload = {
            'user_id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'email': user.email,
            'phone': user.phone,
            'is_active': user.is_active,
            'kyc_status': kyc_status,
            'has_national_id': has_national_id,
            'has_date_of_birth': has_date_of_birth,
            'has_primary_address': has_primary_address,
            'has_bank_account': has_bank_account,
            'is_usd_endorsed': is_usd_endorsed,
            'latest_endorsement_status': latest_endorsement.status if latest_endorsement else None,
            'missing_fields': missing_fields,
        }
        logger.info(
            'Internal KYC status queried',
            extra={'user_id': user.id, 'kyc_status': kyc_status},
        )
        return Response(InternalKYCStatusSerializer(payload).data)

