import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView

from core.permissions import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MANAGER, ROLE_SUPERADMIN, IsAdminOrAbove, get_user_role
from .audit import record_activity
from .models import ActivityLog, Address, CustomUser, Role
from .permissions import CanManageUser, IsOwner
from .serializers import (
    ActivityLogSerializer,
    AddressSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeUpdateSerializer,
    OpenBankAccountSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

logger = logging.getLogger('finchat.accounts')


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_obj = getattr(serializer, 'user_instance', None)
        if user_obj is not None:
            record_activity(
                request=request,
                actor=user_obj,
                subject_user=user_obj,
                category=ActivityLog.Category.AUTH,
                action='LOGIN',
                description=f'{user_obj.username} signed in ({user_obj.role.name})',
                metadata={'role': user_obj.role.name},
            )
        logger.info(
            'User logged in',
            extra={'username': serializer.validated_data['user']['username']},
        )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class RefreshTokenView(TokenRefreshView):
    permission_classes = [AllowAny]


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=LogoutSerializer, responses={200: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = serializer.save()
        except TokenError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        actor = request.user if request.user and request.user.is_authenticated else None
        if actor is None:
            token_user_id = token.payload.get('user_id')
            if token_user_id is not None:
                actor = CustomUser.objects.filter(id=token_user_id).first()

        if actor is not None:
            record_activity(
                request=request,
                actor=actor,
                subject_user=actor,
                category=ActivityLog.Category.AUTH,
                action='LOGOUT',
                description=f'{actor.username} signed out',
            )
            logger.info('User logged out', extra={'user_id': actor.id})
        return Response({'detail': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=MeUpdateSerializer, responses=UserSerializer)
    def patch(self, request):
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_activity(
            request=request,
            actor=request.user,
            subject_user=request.user,
            category=ActivityLog.Category.PROFILE,
            action='PROFILE_UPDATED',
            description=f'{request.user.username} updated personal profile',
        )
        logger.info('User updated own profile', extra={'user_id': request.user.id})
        return Response(UserSerializer(request.user).data)


class RoleListView(generics.ListAPIView):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAdminOrAbove]
    pagination_class = None

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Role.objects.none()
        actor_role = get_user_role(self.request.user)
        if actor_role == ROLE_SUPERADMIN:
            return Role.objects.all()
        return Role.objects.filter(name__in=[ROLE_MANAGER, ROLE_CUSTOMER])


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CanManageUser]
    filterset_fields = ['role__name', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['created_at', 'username']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return CustomUser.objects.none()
        actor_role = get_user_role(self.request.user)
        qs = CustomUser.objects.select_related('role', 'profile', 'bank_account').all()
        if actor_role == ROLE_SUPERADMIN:
            return qs
        if actor_role == ROLE_ADMIN:
            return qs.filter(
                Q(role__name__in=[ROLE_CUSTOMER, ROLE_MANAGER])
                | Q(created_by=self.request.user)
                | Q(id=self.request.user.id)
            )
        return CustomUser.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ('update', 'partial_update'):
            return UserUpdateSerializer
        if self.action == 'open_account':
            return OpenBankAccountSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        record_activity(
            request=request,
            actor=request.user,
            subject_user=user,
            category=ActivityLog.Category.ADMIN,
            action='USER_CREATED',
            description=f'User {user.username} ({user.role.name}) created by {request.user.username}',
            metadata={'role': user.role.name},
        )
        logger.info(
            'User created by admin',
            extra={'created_user_id': user.id, 'role': user.role.name, 'actor_id': request.user.id},
        )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        record_activity(
            request=request,
            actor=request.user,
            subject_user=user,
            category=ActivityLog.Category.ADMIN,
            action='USER_UPDATED',
            description=f'User {user.username} updated by {request.user.username}',
            metadata={'is_active': user.is_active, 'role': user.role.name},
        )
        logger.info(
            'User updated by admin',
            extra={'target_user_id': user.id, 'actor_id': request.user.id},
        )
        return Response(UserSerializer(user).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.id == request.user.id:
            return Response(
                {'detail': 'You cannot delete your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info(
            'User deleted by admin',
            extra={'deleted_user_id': instance.id, 'actor_id': request.user.id},
        )
        return super().destroy(request, *args, **kwargs)

    @extend_schema(request=OpenBankAccountSerializer, responses={201: UserSerializer})
    @action(detail=True, methods=['post'], url_path='open-account')
    @transaction.atomic
    def open_account(self, request, pk=None):
        from apps.banking.models import BankAccount, Transaction

        target_user = self.get_object()
        if BankAccount.objects.filter(user=target_user).exists():
            raise ValidationError('This user already has a bank account.')

        serializer = OpenBankAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_type = serializer.validated_data['account_type']
        initial_balance = serializer.validated_data['initial_balance']

        account = BankAccount.objects.create(
            user=target_user,
            account_type=account_type,
            balance=initial_balance,
            currency='USD',
        )
        if initial_balance > Decimal('0.00'):
            Transaction.objects.create(
                account=account,
                performed_by=request.user,
                transaction_type=Transaction.Type.DEPOSIT,
                channel=Transaction.Channel.SYSTEM,
                amount=initial_balance,
                balance_after=initial_balance,
                description=f'Opening balance on {account_type} account',
            )

        record_activity(
            request=request,
            actor=request.user,
            subject_user=target_user,
            category=ActivityLog.Category.BANKING,
            action='BANK_ACCOUNT_OPENED',
            description=(
                f'Opened {account_type} account {account.account_number} for {target_user.username} '
                f'with balance ${initial_balance}'
            ),
            metadata={
                'account_number': account.account_number,
                'account_type': account_type,
                'initial_balance': str(initial_balance),
            },
        )
        logger.info(
            'Personal bank account opened for user',
            extra={
                'target_user_id': target_user.id,
                'account_number': account.account_number,
                'actor_id': request.user.id,
            },
        )
        target_user.refresh_from_db()
        return Response(UserSerializer(target_user).data, status=status.HTTP_201_CREATED)


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    pagination_class = None

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Address.objects.none()
        user = self.request.user
        role_name = get_user_role(user)
        user_id = self.request.query_params.get('user_id')
        if role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER) and user_id:
            return Address.objects.filter(user_id=user_id)
        return Address.objects.filter(user=user)

    def perform_create(self, serializer):
        address = serializer.save(user=self.request.user)
        record_activity(
            request=self.request,
            actor=self.request.user,
            subject_user=self.request.user,
            category=ActivityLog.Category.PROFILE,
            action='ADDRESS_CREATED',
            description=f'Added {address.label} address in {address.city}, {address.country}',
            metadata={'address_id': address.id, 'label': address.label},
        )
        logger.info(
            'Address created',
            extra={'address_id': address.id, 'user_id': self.request.user.id},
        )

    def perform_update(self, serializer):
        address = serializer.save()
        record_activity(
            request=self.request,
            actor=self.request.user,
            subject_user=address.user,
            category=ActivityLog.Category.PROFILE,
            action='ADDRESS_UPDATED',
            description=f'Updated {address.label} address in {address.city}',
            metadata={'address_id': address.id, 'label': address.label},
        )
        logger.info(
            'Address updated',
            extra={'address_id': address.id, 'user_id': self.request.user.id},
        )

    def perform_destroy(self, instance):
        record_activity(
            request=self.request,
            actor=self.request.user,
            subject_user=instance.user,
            category=ActivityLog.Category.PROFILE,
            action='ADDRESS_DELETED',
            description=f'Removed {instance.label} address in {instance.city}',
            metadata={'address_id': instance.id, 'label': instance.label},
        )
        logger.info(
            'Address deleted',
            extra={'address_id': instance.id, 'user_id': self.request.user.id},
        )
        instance.delete()


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['category', 'action', 'subject_user', 'actor']
    search_fields = [
        'action',
        'description',
        'actor__username',
        'subject_user__username',
        'subject_user__first_name',
        'subject_user__last_name',
    ]
    ordering_fields = ['created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ActivityLog.objects.none()
        user = self.request.user
        role_name = get_user_role(user)
        qs = ActivityLog.objects.select_related('actor', 'actor__role', 'subject_user')
        mine = self.request.query_params.get('mine')
        if role_name in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER) and mine != 'true':
            return qs
        return qs.filter(subject_user=user)

