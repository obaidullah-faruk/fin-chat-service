import logging

from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.banking.models import BankAccount
from apps.endorsement.models import Endorsement
from core.internal_auth import HasInternalAPIKey, get_internal_user
from core.permissions import ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERADMIN
from .audit import record_activity
from .models import ActivityLog, Address, CustomUser, UserProfile
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
        parameters=[
            OpenApiParameter('target_user_id', int, required=False),
        ],
        responses=InternalKYCStatusSerializer,
    )
    def get(self, request):
        user = get_internal_user(request)
        role_name = getattr(user.role, 'name', '') if user.role else 'customer'
        is_staff = role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER)

        target_user = user
        target_param = request.query_params.get('target_user_id') or request.query_params.get('user_id')
        if is_staff and target_param and str(target_param).strip().isdigit():
            found_user = CustomUser.objects.filter(pk=int(target_param)).first()
            if found_user:
                target_user = found_user

        profile = UserProfile.objects.filter(user=target_user).first()
        primary_address = Address.objects.filter(user=target_user, is_primary=True).first()
        account = BankAccount.objects.filter(user=target_user).first()
        latest_endorsement = (
            Endorsement.objects.filter(requester=target_user).order_by('-created_at').first()
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
        elif has_national_id or has_date_of_birth or has_primary_address or bool(target_user.phone.strip()):
            kyc_status = 'partial'
        else:
            kyc_status = 'incomplete'

        payload = {
            'user_id': target_user.id,
            'username': target_user.username,
            'full_name': target_user.full_name,
            'email': target_user.email,
            'phone': target_user.phone,
            'is_active': target_user.is_active,
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
            extra={'user_id': user.id, 'target_user_id': target_user.id, 'kyc_status': kyc_status},
        )
        return Response(InternalKYCStatusSerializer(payload).data)


class InternalCustomerLookupView(_BaseInternalServiceView):
    @extend_schema(
        tags=['Internal Service'],
        parameters=[
            OpenApiParameter('query', str, required=True),
        ],
    )
    def get(self, request):
        user = get_internal_user(request)
        role_name = getattr(user.role, 'name', '') if user.role else 'customer'
        is_staff = role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER)
        if not is_staff:
            raise PermissionDenied('Staff privileges required for customer lookup.')

        raw_query = request.query_params.get('query', '').strip()
        if not raw_query:
            raise ValidationError({'detail': 'query parameter is required.'})

        qs = CustomUser.objects.select_related('role', 'profile', 'bank_account')
        target_user = None
        if raw_query.isdigit():
            target_user = qs.filter(pk=int(raw_query)).first()

        if not target_user:
            target_user = qs.filter(
                Q(username__iexact=raw_query)
                | Q(email__iexact=raw_query)
                | Q(bank_account__account_number__iexact=raw_query)
            ).first()

        if not target_user:
            target_user = qs.filter(
                Q(username__icontains=raw_query)
                | Q(first_name__icontains=raw_query)
                | Q(last_name__icontains=raw_query)
                | Q(email__icontains=raw_query)
            ).first()

        if not target_user:
            raise NotFound(f"Customer matching '{raw_query}' not found.")

        account = getattr(target_user, 'bank_account', None)
        profile = getattr(target_user, 'profile', None)
        primary_address = Address.objects.filter(user=target_user, is_primary=True).first()

        data = {
            'user_id': target_user.id,
            'username': target_user.username,
            'full_name': target_user.full_name,
            'email': target_user.email,
            'phone': target_user.phone,
            'role': target_user.role.name if target_user.role else 'customer',
            'is_active': target_user.is_active,
            'account_number': account.account_number if account else None,
            'account_type': account.account_type if account else None,
            'balance': str(account.balance) if account else None,
            'account_is_active': account.is_active if account else None,
            'is_usd_endorsed': account.is_usd_endorsed if account else False,
            'has_national_id': bool(profile and profile.national_id.strip()),
            'primary_address': primary_address.city if primary_address else None,
            'created_at': target_user.created_at.isoformat(),
        }

        logger.info(
            'Internal customer lookup executed',
            extra={'user_id': user.id, 'role': role_name, 'target_user_id': target_user.id},
        )
        return Response(data)

