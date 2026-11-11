from decimal import Decimal
from rest_framework import serializers

from .models import Endorsement


class EndorsementSerializer(serializers.ModelSerializer):
    requester_username = serializers.CharField(source='requester.username', read_only=True)
    endorser_username = serializers.CharField(
        source='endorser.username', read_only=True, default=None
    )
    account_number = serializers.SerializerMethodField()

    class Meta:
        model = Endorsement
        fields = [
            'id',
            'requester',
            'requester_username',
            'account_number',
            'endorser',
            'endorser_username',
            'endorsement_type',
            'currency',
            'amount',
            'passport_number',
            'status',
            'notes',
            'review_remarks',
            'created_at',
            'reviewed_at',
        ]
        read_only_fields = [
            'id',
            'requester',
            'endorser',
            'currency',
            'status',
            'review_remarks',
            'created_at',
            'reviewed_at',
        ]

    def get_account_number(self, obj) -> str | None:
        account = getattr(obj.requester, 'bank_account', None)
        return account.account_number if account else None


class EndorsementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Endorsement
        fields = ['endorsement_type', 'amount', 'passport_number', 'notes']

    def validate_amount(self, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= Decimal('0.00'):
            raise serializers.ValidationError('Requested USD limit must be greater than zero.')
        return value


class EndorsementReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[Endorsement.Status.APPROVED, Endorsement.Status.REJECTED]
    )
    review_remarks = serializers.CharField(required=False, allow_blank=True, default='')

