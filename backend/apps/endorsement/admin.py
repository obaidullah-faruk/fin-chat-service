from django.contrib import admin

from .models import Endorsement


@admin.register(Endorsement)
class EndorsementAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'requester',
        'endorsement_type',
        'currency',
        'amount',
        'status',
        'endorser',
        'created_at',
    )
    list_filter = ('status', 'endorsement_type', 'currency')
    search_fields = ('requester__username', 'passport_number', 'notes')

