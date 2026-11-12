from decimal import Decimal
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from core.permissions import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MANAGER, ROLE_SUPERADMIN, get_user_role
from .audit import record_activity
from .models import ActivityLog, Address, CustomUser, Role, UserProfile


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'description']


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['date_of_birth', 'national_id', 'bio', 'updated_at']
        read_only_fields = ['updated_at']


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'id',
            'user',
            'label',
            'street',
            'city',
            'state',
            'postal_code',
            'country',
            'is_primary',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source='role.name', read_only=True)
    role_id = serializers.PrimaryKeyRelatedField(
        source='role', queryset=Role.objects.all(), write_only=True, required=False
    )
    profile = UserProfileSerializer(read_only=True)
    bank_account = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'phone',
            'role',
            'role_id',
            'is_active',
            'created_by',
            'created_at',
            'updated_at',
            'profile',
            'bank_account',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_bank_account(self, obj) -> dict | None:
        account = getattr(obj, 'bank_account', None)
        if not account:
            return None
        return {
            'id': account.id,
            'account_number': account.account_number,
            'account_type': account.account_type,
            'balance': str(account.balance),
            'currency': account.currency,
            'is_usd_endorsed': account.is_usd_endorsed,
            'usd_endorsement_limit': str(account.usd_endorsement_limit),
            'is_active': account.is_active,
        }


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.SlugRelatedField(slug_field='name', queryset=Role.objects.all())
    initial_balance = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, default=Decimal('0.00'), write_only=True
    )
    account_type = serializers.ChoiceField(
        choices=[('savings', 'Savings'), ('current', 'Current'), ('salary', 'Salary')],
        required=False,
        default='savings',
        write_only=True,
    )
    create_bank_account = serializers.BooleanField(
        required=False,
        default=False,
        write_only=True,
        help_text='Automatically true for customers; optional for staff roles if they also hold a personal account.',
    )

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'username',
            'email',
            'password',
            'first_name',
            'last_name',
            'phone',
            'role',
            'is_active',
            'initial_balance',
            'account_type',
            'create_bank_account',
        ]

    def validate_role(self, role: Role) -> Role:
        request = self.context.get('request')
        actor_role = get_user_role(request.user) if request else None
        if actor_role == ROLE_ADMIN and role.name in (ROLE_SUPERADMIN, ROLE_ADMIN):
            raise serializers.ValidationError('Admins can only create manager or customer users.')
        return role

    def validate_initial_balance(self, value: Decimal) -> Decimal:
        if value < 0:
            raise serializers.ValidationError('Initial balance cannot be negative.')
        return value

    def create(self, validated_data):
        from apps.banking.models import BankAccount, Transaction

        password = validated_data.pop('password')
        initial_balance = validated_data.pop('initial_balance', Decimal('0.00'))
        account_type = validated_data.pop('account_type', 'savings')
        create_bank_account = validated_data.pop('create_bank_account', False)
        request = self.context.get('request')
        actor = request.user if request and request.user.is_authenticated else None
        if actor:
            validated_data['created_by'] = actor

        with transaction.atomic():
            user = CustomUser.objects.create_user(password=password, **validated_data)
            if user.role.name == ROLE_CUSTOMER or create_bank_account:
                account = BankAccount.objects.create(
                    user=user,
                    account_type=account_type,
                    balance=initial_balance,
                )
                if initial_balance > 0:
                    Transaction.objects.create(
                        account=account,
                        performed_by=actor,
                        transaction_type=Transaction.Type.DEPOSIT,
                        channel=Transaction.Channel.SYSTEM,
                        amount=initial_balance,
                        balance_after=initial_balance,
                        description='Initial opening deposit',
                    )
                record_activity(
                    request=request,
                    actor=actor,
                    subject_user=user,
                    category=ActivityLog.Category.BANKING,
                    action='BANK_ACCOUNT_OPENED',
                    description=f'Opened {account_type} account {account.account_number} with initial balance ${initial_balance}',
                    metadata={
                        'account_number': account.account_number,
                        'account_type': account_type,
                        'initial_balance': str(initial_balance),
                    },
                )
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(
        slug_field='name', queryset=Role.objects.all(), required=False
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name', 'phone', 'role', 'is_active']

    def validate_role(self, role: Role) -> Role:
        request = self.context.get('request')
        actor_role = get_user_role(request.user) if request else None
        if actor_role == ROLE_ADMIN and role.name in (ROLE_SUPERADMIN, ROLE_ADMIN):
            raise serializers.ValidationError('Admins cannot assign admin or superadmin roles.')
        return role


class MeUpdateSerializer(serializers.ModelSerializer):
    date_of_birth = serializers.DateField(source='profile.date_of_birth', required=False, allow_null=True)
    national_id = serializers.CharField(source='profile.national_id', required=False, allow_blank=True)
    bio = serializers.CharField(source='profile.bio', required=False, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'phone', 'date_of_birth', 'national_id', 'bio']

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        profile, _ = UserProfile.objects.get_or_create(user=instance)
        for attr, val in profile_data.items():
            setattr(profile, attr, val)
        profile.save()
        return instance


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(help_text='Username or email address')
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        identifier = attrs.get('username', '').strip()
        password = attrs.get('password', '')

        lookup_username = identifier
        if '@' in identifier:
            user_by_email = CustomUser.objects.filter(email__iexact=identifier).first()
            if user_by_email:
                lookup_username = user_by_email.username

        user = authenticate(username=lookup_username, password=password)
        if not user:
            raise serializers.ValidationError('Invalid username/email or password.')
        if not user.is_active:
            raise serializers.ValidationError('This account is disabled.')

        self.user_instance = user
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def save(self, **kwargs):
        token = RefreshToken(self.validated_data['refresh'])
        token.blacklist()
        return token


class OpenBankAccountSerializer(serializers.Serializer):
    account_type = serializers.ChoiceField(
        choices=[('savings', 'Savings'), ('current', 'Current'), ('salary', 'Salary')],
        default='savings',
    )
    initial_balance = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        default=Decimal('0.00'),
    )

    def validate_initial_balance(self, value: Decimal) -> Decimal:
        if value < Decimal('0.00'):
            raise serializers.ValidationError('Initial balance cannot be negative.')
        return value


class ActivityLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True, default=None)
    actor_role = serializers.SerializerMethodField()
    subject_username = serializers.CharField(source='subject_user.username', read_only=True)
    subject_full_name = serializers.CharField(source='subject_user.full_name', read_only=True)

    class Meta:
        model = ActivityLog
        fields = [
            'id',
            'actor',
            'actor_username',
            'actor_role',
            'subject_user',
            'subject_username',
            'subject_full_name',
            'category',
            'action',
            'description',
            'metadata',
            'ip_address',
            'created_at',
        ]

    def get_actor_role(self, obj) -> str | None:
        if obj.actor and obj.actor.role:
            return obj.actor.role.name
        return None


class InternalAddressUpsertSerializer(serializers.Serializer):
    address_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    label = serializers.ChoiceField(
        choices=Address.Label.choices,
        required=False,
        default=Address.Label.HOME,
    )
    street = serializers.CharField()
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    postal_code = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=100)
    is_primary = serializers.BooleanField(required=False, default=True)


class InternalKYCStatusSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField()
    kyc_status = serializers.ChoiceField(choices=['verified', 'partial', 'incomplete'])
    has_national_id = serializers.BooleanField()
    has_date_of_birth = serializers.BooleanField()
    has_primary_address = serializers.BooleanField()
    has_bank_account = serializers.BooleanField()
    is_usd_endorsed = serializers.BooleanField()
    latest_endorsement_status = serializers.CharField(allow_null=True)
    missing_fields = serializers.ListField(child=serializers.CharField())


