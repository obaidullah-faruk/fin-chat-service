import random
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models


def generate_account_number() -> str:
    while True:
        candidate = f'FC{random.randint(1000000000, 9999999999)}'
        if not BankAccount.objects.filter(account_number=candidate).exists():
            return candidate


def generate_transaction_reference() -> str:
    return f'TXN-{uuid.uuid4().hex[:12].upper()}'


class BankAccount(models.Model):
    class AccountType(models.TextChoices):
        SAVINGS = 'savings', 'Savings'
        CURRENT = 'current', 'Current'
        SALARY = 'salary', 'Salary'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bank_account',
    )
    account_number = models.CharField(max_length=20, unique=True, blank=True)
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.SAVINGS,
    )
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default='USD')
    is_usd_endorsed = models.BooleanField(default=False)
    usd_endorsement_limit = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.account_number:
            self.account_number = generate_account_number()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.account_number} ({self.user.username})'


class Transaction(models.Model):
    class Type(models.TextChoices):
        DEPOSIT = 'deposit', 'Deposit'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
        TRANSFER_IN = 'transfer_in', 'Transfer In'
        TRANSFER_OUT = 'transfer_out', 'Transfer Out'

    class Channel(models.TextChoices):
        ONLINE = 'online', 'Online / Digital'
        ATM = 'atm', 'ATM'
        BRANCH_TELLER = 'branch_teller', 'Branch Teller'
        SYSTEM = 'system', 'System / Opening'

    account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='transactions',
    )
    related_account = models.ForeignKey(
        BankAccount,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='related_transactions',
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='performed_transactions',
    )
    transaction_type = models.CharField(max_length=20, choices=Type.choices)
    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
        default=Channel.ONLINE,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    reference = models.CharField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_transaction_reference()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.reference} [{self.transaction_type}] {self.amount}'

