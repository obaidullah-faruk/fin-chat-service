from decimal import Decimal
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import CustomUser
from apps.banking.models import BankAccount


class EndorsementTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.login_url = reverse('auth-login')
        self.endorsement_url = reverse('endorsement-list-create')

    def _authenticate(self, username: str):
        resp = self.client.post(self.login_url, {'username': username, 'password': 'Test@1234'})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_usd_endorsement_request_and_approval(self):
        self._authenticate('customer1')
        resp = self.client.post(
            self.endorsement_url,
            {
                'endorsement_type': 'usd_enable',
                'amount': '3000.00',
                'passport_number': 'P1234567',
                'notes': 'International software subscriptions',
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        end_id = resp.data['id']
        self.assertEqual(resp.data['currency'], 'USD')

        review_url = reverse('endorsement-review', args=[end_id])
        # Customer forbidden
        self.assertEqual(
            self.client.patch(review_url, {'status': 'approved'}).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Manager approves -> updates BankAccount USD endorsement
        self._authenticate('manager1')
        approve = self.client.patch(
            review_url, {'status': 'approved', 'review_remarks': 'Passport checked'}
        )
        self.assertEqual(approve.status_code, status.HTTP_200_OK)
        self.assertEqual(approve.data['status'], 'approved')

        acc = BankAccount.objects.get(user__username='customer1')
        self.assertTrue(acc.is_usd_endorsed)
        self.assertEqual(acc.usd_endorsement_limit, Decimal('3000.00'))

    def test_separation_of_duties_prevents_self_endorsement_approval(self):
        superadmin = CustomUser.objects.get(username='superadmin')
        self._authenticate('superadmin')
        self.client.post(
            reverse('user-open-account', args=[superadmin.id]),
            {'account_type': 'savings', 'initial_balance': '1000.00'},
        )
        req_resp = self.client.post(
            self.endorsement_url,
            {'endorsement_type': 'usd_enable', 'amount': '2000.00'},
        )
        self.assertEqual(req_resp.status_code, status.HTTP_201_CREATED)

        review_url = reverse('endorsement-review', args=[req_resp.data['id']])
        self_approve = self.client.patch(review_url, {'status': 'approved'})
        self.assertEqual(self_approve.status_code, status.HTTP_400_BAD_REQUEST)

