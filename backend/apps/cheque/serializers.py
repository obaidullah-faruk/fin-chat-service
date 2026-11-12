from rest_framework import serializers

from apps.accounts.models import Address
from .models import ChequeBookRequest


ALLOWED_LEAF_COUNTS = (10, 25, 50, 100)


class ChequeBookRequestSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    account_number = serializers.SerializerMethodField()
    reviewed_by_username = serializers.CharField(
        source='reviewed_by.username', read_only=True, default=None
    )

    class Meta:
        model = ChequeBookRequest
        fields = [
            'id',
            'user',
            'username',
            'account_number',
            'leaves_requested',
            'delivery_address',
            'delivery_address_snapshot',
            'status',
            'reviewed_by',
            'reviewed_by_username',
            'remarks',
            'requested_at',
            'reviewed_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'delivery_address_snapshot',
            'status',
            'reviewed_by',
            'remarks',
            'requested_at',
            'reviewed_at',
        ]

    def get_account_number(self, obj) -> str | None:
        account = getattr(obj.user, 'bank_account', None)
        return account.account_number if account else None


class ChequeBookCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChequeBookRequest
        fields = ['leaves_requested', 'delivery_address', 'remarks']
        extra_kwargs = {'remarks': {'required': False, 'allow_blank': True}}

    def validate_leaves_requested(self, value: int) -> int:
        if value not in ALLOWED_LEAF_COUNTS:
            raise serializers.ValidationError(
                f'Leaves requested must be one of {ALLOWED_LEAF_COUNTS}.'
            )
        return value

    def validate_delivery_address(self, address: Address | None) -> Address | None:
        request = self.context.get('request')
        if address and request and address.user_id != request.user.id:
            raise serializers.ValidationError('Selected delivery address does not belong to you.')
        return address


class ChequeBookReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            ChequeBookRequest.Status.APPROVED,
            ChequeBookRequest.Status.REJECTED,
            ChequeBookRequest.Status.ISSUED,
        ]
    )
    remarks = serializers.CharField(required=False, allow_blank=True, default='')


class InternalChequeRequestCreateSerializer(serializers.Serializer):
    leaves_requested = serializers.IntegerField(required=False, default=25)
    delivery_address_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    remarks = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_leaves_requested(self, value: int) -> int:
        if value not in ALLOWED_LEAF_COUNTS:
            raise serializers.ValidationError(
                f'Leaves requested must be one of {ALLOWED_LEAF_COUNTS}.'
            )
        return value


