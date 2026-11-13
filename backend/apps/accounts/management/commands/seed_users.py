import logging
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.audit import record_activity
from apps.accounts.models import ActivityLog, Address, CustomUser, Role, UserProfile
from apps.banking.models import BankAccount, Transaction

logger = logging.getLogger('finchat.seed')


ROLE_DEFINITIONS = [
    (Role.Name.SUPERADMIN, 'Full system administrator'),
    (Role.Name.ADMIN, 'Manage users and view all transactions'),
    (Role.Name.MANAGER, 'Approve or reject cheque books and USD endorsements'),
    (Role.Name.CUSTOMER, 'Standard customer banking access'),
]

SEED_USERS = [
    {
        'username': 'superadmin',
        'email': 'superadmin@finchat.local',
        'first_name': 'Super',
        'last_name': 'Admin',
        'role': Role.Name.SUPERADMIN,
        'is_staff': True,
        'is_superuser': True,
        'balance': None,
    },
    {
        'username': 'admin1',
        'email': 'admin1@finchat.local',
        'first_name': 'System',
        'last_name': 'Admin',
        'role': Role.Name.ADMIN,
        'is_staff': True,
        'is_superuser': False,
        'balance': None,
    },
    {
        'username': 'manager1',
        'email': 'manager1@finchat.local',
        'first_name': 'Branch',
        'last_name': 'Manager',
        'role': Role.Name.MANAGER,
        'is_staff': False,
        'is_superuser': False,
        'balance': None,
    },
    {
        'username': 'customer1',
        'email': 'customer1@finchat.local',
        'first_name': 'Alice',
        'last_name': 'Rahman',
        'role': Role.Name.CUSTOMER,
        'is_staff': False,
        'is_superuser': False,
        'balance': Decimal('10000.00'),
        'account_number': 'FC1000000001',
        'account_type': 'savings',
        'address': {
            'label': 'home',
            'street': '42 Gulshan Avenue',
            'city': 'Dhaka',
            'state': 'Dhaka',
            'postal_code': '1212',
            'country': 'Bangladesh',
        },
    },
    {
        'username': 'customer2',
        'email': 'customer2@finchat.local',
        'first_name': 'Bob',
        'last_name': 'Karim',
        'role': Role.Name.CUSTOMER,
        'is_staff': False,
        'is_superuser': False,
        'balance': Decimal('5000.00'),
        'account_number': 'FC1000000002',
        'account_type': 'current',
        'address': {
            'label': 'home',
            'street': '15 Banani Road 11',
            'city': 'Dhaka',
            'state': 'Dhaka',
            'postal_code': '1213',
            'country': 'Bangladesh',
        },
    },
    {
        'username': 'customer3',
        'email': 'customer3@finchat.local',
        'first_name': 'Clara',
        'last_name': 'Ahmed',
        'role': Role.Name.CUSTOMER,
        'is_staff': False,
        'is_superuser': False,
        'balance': Decimal('2500.00'),
        'account_number': 'FC1000000003',
        'account_type': 'savings',
        'address': {
            'label': 'home',
            'street': '88 Dhanmondi 27',
            'city': 'Dhaka',
            'state': 'Dhaka',
            'postal_code': '1209',
            'country': 'Bangladesh',
        },
    },
]


class Command(BaseCommand):
    help = 'Seed RBAC roles, test users, and initial customer bank accounts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--with-staff-accounts',
            action='store_true',
            help='Also create personal bank accounts for staff users (superadmin, manager1) for dual-mode testing.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        with_staff_accounts = options.get('with_staff_accounts', False)
        default_password = getattr(settings, 'SEED_DEFAULT_PASSWORD', 'Test@1234')

        roles = {}
        for role_name, description in ROLE_DEFINITIONS:
            role, _ = Role.objects.get_or_create(
                name=role_name,
                defaults={'description': description},
            )
            roles[role_name] = role

        created_count = 0
        for entry in SEED_USERS:
            user, created = CustomUser.objects.get_or_create(
                username=entry['username'],
                defaults={
                    'email': entry['email'],
                    'first_name': entry['first_name'],
                    'last_name': entry['last_name'],
                    'role': roles[entry['role']],
                    'is_staff': entry['is_staff'],
                    'is_superuser': entry['is_superuser'],
                    'is_active': True,
                },
            )
            if created:
                user.set_password(default_password)
                user.save(update_fields=['password'])
                UserProfile.objects.get_or_create(user=user)
                created_count += 1

                if entry['balance'] is not None:
                    account = BankAccount.objects.create(
                        user=user,
                        account_number=entry['account_number'],
                        account_type=entry['account_type'],
                        balance=entry['balance'],
                        currency='USD',
                    )
                    Transaction.objects.create(
                        account=account,
                        transaction_type=Transaction.Type.DEPOSIT,
                        channel=Transaction.Channel.SYSTEM,
                        amount=entry['balance'],
                        balance_after=entry['balance'],
                        description='Seeded initial opening balance',
                    )
                    record_activity(
                        subject_user=user,
                        category=ActivityLog.Category.BANKING,
                        action='BANK_ACCOUNT_OPENED',
                        description=(
                            f'Seeded {entry["account_type"]} account {entry["account_number"]} '
                            f'with opening balance ${entry["balance"]}'
                        ),
                        metadata={
                            'account_number': entry['account_number'],
                            'account_type': entry['account_type'],
                            'initial_balance': str(entry['balance']),
                        },
                    )

                addr_data = entry.get('address')
                if addr_data:
                    Address.objects.create(user=user, is_primary=True, **addr_data)

            if with_staff_accounts and not BankAccount.objects.filter(user=user).exists() and entry['role'] in (Role.Name.SUPERADMIN, Role.Name.MANAGER):
                staff_acct = BankAccount.objects.create(
                    user=user,
                    account_type=BankAccount.AccountType.CURRENT,
                    balance=Decimal('50000.00'),
                    currency='USD',
                )
                Transaction.objects.create(
                    account=staff_acct,
                    transaction_type=Transaction.Type.DEPOSIT,
                    channel=Transaction.Channel.SYSTEM,
                    amount=Decimal('50000.00'),
                    balance_after=Decimal('50000.00'),
                    description='Seeded staff test opening balance',
                )
                self.stdout.write(
                    self.style.NOTICE(f'Attached test bank account {staff_acct.account_number} to {user.username}')
                )

        logger.info('Seed users completed', extra={'newly_created_users': created_count})
        self.stdout.write(
            self.style.SUCCESS(
                f'Seeder finished successfully ({created_count} new users created).'
            )
        )

