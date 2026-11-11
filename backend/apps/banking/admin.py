from django.contrib import admin

from .models import BankAccount, Transaction


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'account_number',
        'user',
        'account_type',
        'balance',
        'currency',
        'is_usd_endorsed',
        'is_active',
    )
    list_filter = ('account_type', 'currency', 'is_usd_endorsed', 'is_active')
    search_fields = ('account_number', 'user__username', 'user__email')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'reference',
        'account',
        'transaction_type',
        'channel',
        'performed_by',
        'amount',
        'balance_after',
        'created_at',
    )
    list_filter = ('transaction_type', 'channel', 'created_at')
    search_fields = ('reference', 'account__account_number', 'description', 'performed_by__username')

