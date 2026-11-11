from decimal import Decimal
from django.core.management import call_command
from django.urls import reverse
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

