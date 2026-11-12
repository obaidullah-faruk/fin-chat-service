from datetime import timedelta
from decimal import Decimal
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import CustomUser
from apps.banking.models import BankAccount, Transaction


class BankingTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.login_url = reverse('auth-login')
        self.account_url = reverse('banking-account')
        self.deposit_url = reverse('banking-deposit')
        self.withdraw_url = reverse('banking-withdraw')
        self.transfer_url = reverse('banking-transfer')
        self.txns_url = reverse('transaction-list')

    def _authenticate(self, username: str):
        resp = self.client.post(self.login_url, {'username': username, 'password': 'Test@1234'})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_change_account_type(self):
        self._authenticate('customer1')
        resp = self.client.patch(self.account_url, {'account_type': 'current'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['account_type'], 'current')

    def test_deposit_withdraw_and_transfer_flow(self):
        self._authenticate('customer1')

        # Deposit 500 -> 10500
        dep = self.client.post(self.deposit_url, {'amount': '500.00', 'description': 'Bonus'})
        self.assertEqual(dep.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(dep.data['balance_after']), Decimal('10500.00'))

        # Withdraw 200 -> 10300
        wd = self.client.post(self.withdraw_url, {'amount': '200.00'})
        self.assertEqual(wd.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(wd.data['balance_after']), Decimal('10300.00'))

        # Over-withdraw rejected
        over_wd = self.client.post(self.withdraw_url, {'amount': '999999.00'})
        self.assertEqual(over_wd.status_code, status.HTTP_400_BAD_REQUEST)

        # Transfer 300 to customer2 (FC1000000002)
        tr = self.client.post(
            self.transfer_url,
            {'to_account_number': 'FC1000000002', 'amount': '300.00', 'description': 'Rent'},
        )
        self.assertEqual(tr.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(tr.data['balance_after']), Decimal('10000.00'))

        c2_acc = BankAccount.objects.get(account_number='FC1000000002')
        self.assertEqual(c2_acc.balance, Decimal('5300.00'))

        # Self transfer rejected
        self_tr = self.client.post(
            self.transfer_url,
            {'to_account_number': 'FC1000000001', 'amount': '50.00'},
        )
        self.assertEqual(self_tr.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_view_all_transactions(self):
        self._authenticate('admin1')
        resp = self.client.get(f'{self.txns_url}?scope=all')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data['count'], 3)

    def test_manager_customer_360_teller_ops_and_freeze(self):
        customer1 = CustomUser.objects.get(username='customer1')
        self._authenticate('manager1')

        # Manager can list customers and inspect Customer 360
        cust_list = self.client.get(reverse('banking-customer-list'))
        self.assertEqual(cust_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(cust_list.data['count'], 3)

        detail_resp = self.client.get(reverse('banking-customer-detail', args=[customer1.id]))
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_resp.data['user']['username'], 'customer1')
        self.assertGreaterEqual(len(detail_resp.data['addresses']), 1)

        # Manager can view all transactions + customer-filtered transactions
        all_txns = self.client.get(f'{self.txns_url}?scope=all&user_id={customer1.id}')
        self.assertEqual(all_txns.status_code, status.HTTP_200_OK)
        self.assertTrue(
            all(item['user_id'] == customer1.id for item in all_txns.data['results'])
        )

        # Branch teller deposit & withdrawal
        teller_dep = self.client.post(
            reverse('banking-teller-deposit', args=[customer1.id]),
            {'amount': '400.00', 'description': 'Counter cash deposit'},
        )
        self.assertEqual(teller_dep.status_code, status.HTTP_201_CREATED)
        self.assertEqual(teller_dep.data['channel'], Transaction.Channel.BRANCH_TELLER)
        self.assertEqual(teller_dep.data['performed_by_username'], 'manager1')
        self.assertEqual(Decimal(teller_dep.data['balance_after']), Decimal('10400.00'))

        teller_wd = self.client.post(
            reverse('banking-teller-withdraw', args=[customer1.id]),
            {'amount': '150.00'},
        )
        self.assertEqual(teller_wd.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(teller_wd.data['balance_after']), Decimal('10250.00'))

        # Freeze account -> blocks customer deposit/withdrawal
        freeze = self.client.patch(
            reverse('banking-customer-account', args=[customer1.id]),
            {'is_active': False, 'reason': 'Compliance review'},
        )
        self.assertEqual(freeze.status_code, status.HTTP_200_OK)
        self.assertFalse(freeze.data['is_active'])

        self._authenticate('customer1')
        frozen_dep = self.client.post(
            self.deposit_url,
            {'amount': '50.00', 'funding_source': 'debit_card'},
        )
        self.assertEqual(frozen_dep.status_code, status.HTTP_400_BAD_REQUEST)

        # Unfreeze restores access
        self._authenticate('manager1')
        unfreeze = self.client.patch(
            reverse('banking-customer-account', args=[customer1.id]),
            {'is_active': True},
        )
        self.assertEqual(unfreeze.status_code, status.HTTP_200_OK)
        self.assertTrue(unfreeze.data['is_active'])

    def test_superadmin_personal_account_isolation_and_sod(self):
        superadmin = CustomUser.objects.get(username='superadmin')
        self._authenticate('superadmin')

        open_resp = self.client.post(
            reverse('user-open-account', args=[superadmin.id]),
            {'account_type': 'savings', 'initial_balance': '2000.00'},
        )
        self.assertEqual(open_resp.status_code, status.HTTP_201_CREATED)

        # scope=mine returns ONLY superadmin's personal transactions, NOT customer1's
        mine_txns = self.client.get(f'{self.txns_url}?scope=mine')
        self.assertEqual(mine_txns.status_code, status.HTTP_200_OK)
        self.assertEqual(mine_txns.data['count'], 1)
        self.assertEqual(mine_txns.data['results'][0]['username'], 'superadmin')

        # scope=all returns bank-wide transactions across customers
        all_txns = self.client.get(f'{self.txns_url}?scope=all')
        self.assertGreaterEqual(all_txns.data['count'], 4)

        # Separation of Duties: superadmin cannot execute teller ops or status update on own account
        self_teller = self.client.post(
            reverse('banking-teller-deposit', args=[superadmin.id]),
            {'amount': '500.00'},
        )
        self.assertEqual(self_teller.status_code, status.HTTP_400_BAD_REQUEST)

        self_freeze = self.client.patch(
            reverse('banking-customer-account', args=[superadmin.id]),
            {'is_active': False},
        )
        self.assertEqual(self_freeze.status_code, status.HTTP_400_BAD_REQUEST)

        # Self-service deposit works for personal account
        self_dep = self.client.post(
            self.deposit_url,
            {'amount': '250.00', 'funding_source': 'atm_cash'},
        )
        self.assertEqual(self_dep.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self_dep.data['channel'], Transaction.Channel.ATM)
        self.assertEqual(Decimal(self_dep.data['balance_after']), Decimal('2250.00'))


@override_settings(INTERNAL_API_KEY='test-internal-secret')
class InternalBankingTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.customer1 = CustomUser.objects.get(username='customer1')
        self.admin1 = CustomUser.objects.get(username='admin1')
        self.balance_url = reverse('internal-banking-balance')
        self.account_info_url = reverse('internal-banking-account-info')
        self.transactions_url = reverse('internal-banking-transactions')
        self.statement_url = reverse('internal-banking-statement')
        self.valid_headers = {
            'HTTP_X_INTERNAL_KEY': 'test-internal-secret',
            'HTTP_X_USER_ID': str(self.customer1.id),
        }

    def test_all_internal_endpoints_reject_missing_or_wrong_key(self):
        login_resp = self.client.post(
            reverse('auth-login'),
            {'username': 'customer1', 'password': 'Test@1234'},
        )
        jwt_token = login_resp.data['access']

        for url in (
            self.balance_url,
            self.account_info_url,
            self.transactions_url,
            self.statement_url,
        ):
            # No credentials
            self.client.credentials()
            self.assertEqual(
                self.client.get(url, HTTP_X_USER_ID=str(self.customer1.id)).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            # Wrong internal key
            self.assertEqual(
                self.client.get(
                    url,
                    HTTP_X_INTERNAL_KEY='wrong-key',
                    HTTP_X_USER_ID=str(self.customer1.id),
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            # External JWT alone without X-Internal-Key is still rejected
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {jwt_token}')
            self.assertEqual(
                self.client.get(url, HTTP_X_USER_ID=str(self.customer1.id)).status_code,
                status.HTTP_403_FORBIDDEN,
            )
        self.client.credentials()

    def test_internal_endpoints_reject_missing_account_or_invalid_user(self):
        # Missing X-User-Id
        resp = self.client.get(
            self.balance_url,
            HTTP_X_INTERNAL_KEY='test-internal-secret',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # User exists but has no bank account (admin1)
        resp = self.client.get(
            self.balance_url,
            HTTP_X_INTERNAL_KEY='test-internal-secret',
            HTTP_X_USER_ID=str(self.admin1.id),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_internal_balance_returns_seeded_customer1_data(self):
        resp = self.client.get(self.balance_url, **self.valid_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['account_number'], 'FC1000000001')
        self.assertEqual(resp.data['account_type'], 'savings')
        self.assertEqual(Decimal(resp.data['balance']), Decimal('10000.00'))
        self.assertEqual(resp.data['currency'], 'USD')
        self.assertTrue(resp.data['is_active'])

    def test_internal_account_info_returns_full_details(self):
        resp = self.client.get(self.account_info_url, **self.valid_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['account_number'], 'FC1000000001')
        self.assertEqual(resp.data['account_type'], 'savings')
        self.assertEqual(Decimal(resp.data['balance']), Decimal('10000.00'))
        self.assertEqual(resp.data['currency'], 'USD')
        self.assertFalse(resp.data['is_usd_endorsed'])
        self.assertEqual(Decimal(resp.data['usd_endorsement_limit']), Decimal('0.00'))
        self.assertTrue(resp.data['is_active'])
        self.assertEqual(resp.data['holder_name'], 'Alice Rahman')
        self.assertEqual(resp.data['username'], 'customer1')
        self.assertEqual(resp.data['email'], 'customer1@finchat.local')

    def test_internal_transactions_supports_limit_and_type_filtering(self):
        account = self.customer1.bank_account
        Transaction.objects.create(
            account=account,
            performed_by=self.customer1,
            transaction_type=Transaction.Type.WITHDRAWAL,
            channel=Transaction.Channel.ATM,
            amount=Decimal('250.00'),
            balance_after=Decimal('9750.00'),
            description='ATM cash withdrawal',
        )
        Transaction.objects.create(
            account=account,
            performed_by=self.customer1,
            transaction_type=Transaction.Type.DEPOSIT,
            channel=Transaction.Channel.ONLINE,
            amount=Decimal('500.00'),
            balance_after=Decimal('10250.00'),
            description='Online top up',
        )

        # Default returns all 3 transactions ordered newest-first
        resp = self.client.get(self.transactions_url, **self.valid_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['account_number'], 'FC1000000001')
        self.assertEqual(resp.data['count'], 3)
        self.assertEqual(len(resp.data['transactions']), 3)

        # Limit parameter
        limited = self.client.get(f'{self.transactions_url}?limit=2', **self.valid_headers)
        self.assertEqual(limited.status_code, status.HTTP_200_OK)
        self.assertEqual(limited.data['count'], 2)
        self.assertEqual(limited.data['transactions'][0]['description'], 'Online top up')

        # transaction_type filter
        filtered = self.client.get(
            f'{self.transactions_url}?transaction_type=withdrawal',
            **self.valid_headers,
        )
        self.assertEqual(filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(filtered.data['count'], 1)
        self.assertEqual(filtered.data['transactions'][0]['transaction_type'], 'withdrawal')

        # Invalid limit / transaction_type rejected with 400
        self.assertEqual(
            self.client.get(f'{self.transactions_url}?limit=0', **self.valid_headers).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.get(f'{self.transactions_url}?limit=abc', **self.valid_headers).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.get(
                f'{self.transactions_url}?transaction_type=invalid',
                **self.valid_headers,
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_internal_statement_filters_by_dates_and_returns_summary(self):
        account = self.customer1.bank_account
        old_txn = Transaction.objects.create(
            account=account,
            performed_by=self.customer1,
            transaction_type=Transaction.Type.WITHDRAWAL,
            channel=Transaction.Channel.ATM,
            amount=Decimal('100.00'),
            balance_after=Decimal('9900.00'),
            description='Old withdrawal',
        )
        past_dt = timezone.now() - timedelta(days=15)
        Transaction.objects.filter(pk=old_txn.pk).update(created_at=past_dt)

        today = timezone.now().date()
        start_recent = (today - timedelta(days=3)).isoformat()
        end_recent = today.isoformat()

        # Full statement (no date filters) includes both seeded deposit and old withdrawal
        full_resp = self.client.get(self.statement_url, **self.valid_headers)
        self.assertEqual(full_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(full_resp.data['account']['account_number'], 'FC1000000001')
        self.assertEqual(full_resp.data['summary']['transaction_count'], 2)
        self.assertEqual(Decimal(full_resp.data['summary']['total_deposits']), Decimal('10000.00'))
        self.assertEqual(Decimal(full_resp.data['summary']['total_withdrawals']), Decimal('100.00'))

        # Date-filtered statement excludes the 15-day-old withdrawal
        filtered_resp = self.client.get(
            f'{self.statement_url}?start_date={start_recent}&end_date={end_recent}',
            **self.valid_headers,
        )
        self.assertEqual(filtered_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(filtered_resp.data['period']['start_date'], start_recent)
        self.assertEqual(filtered_resp.data['period']['end_date'], end_recent)
        self.assertEqual(filtered_resp.data['summary']['transaction_count'], 1)
        self.assertEqual(
            Decimal(filtered_resp.data['summary']['total_withdrawals']),
            Decimal('0.00'),
        )
        self.assertEqual(len(filtered_resp.data['transactions']), 1)

        # Invalid dates or inverted range return 400
        self.assertEqual(
            self.client.get(
                f'{self.statement_url}?start_date=not-a-date',
                **self.valid_headers,
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.get(
                f'{self.statement_url}?start_date=2026-05-10&end_date=2026-05-01',
                **self.valid_headers,
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

