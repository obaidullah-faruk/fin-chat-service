from django.contrib import admin

from .models import ChequeBookRequest


@admin.register(ChequeBookRequest)
class ChequeBookRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'leaves_requested',
        'status',
        'reviewed_by',
        'requested_at',
        'reviewed_at',
    )
    list_filter = ('status', 'leaves_requested')
    search_fields = ('user__username', 'remarks')

