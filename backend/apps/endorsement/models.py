from django.conf import settings
from django.db import models


class Endorsement(models.Model):
    class Type(models.TextChoices):
        USD_ENABLE = 'usd_enable', 'USD Usage Enablement'
        USD_LIMIT = 'usd_limit', 'USD Limit Increase'
        TRAVEL_QUOTA = 'travel_quota', 'USD Travel Quota'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='endorsements_made',
    )
    endorser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='endorsements_given',
    )
    endorsement_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.USD_ENABLE,
    )
    currency = models.CharField(max_length=3, default='USD')
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    passport_number = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True)
    review_remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'Endorsement#{self.id} ({self.requester.username} - {self.currency} - {self.status})'

