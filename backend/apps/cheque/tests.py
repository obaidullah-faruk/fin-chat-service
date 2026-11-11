from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import CustomUser


class ChequeBookTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.login_url = reverse('auth-login')
        self.create_url = reverse('cheque-request-create')
        self.list_url = reverse('cheque-request-list')

    def _authenticate(self, username: str):
        resp = self.client.post(self.login_url, {'username': username, 'password': 'Test@1234'})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_cheque_book_request_and_manager_approval(self):
        self._authenticate('customer1')
        create_resp = self.client.post(self.create_url, {'leaves_requested': 25, 'remarks': 'Urgent'})
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        req_id = create_resp.data['id']
        self.assertEqual(create_resp.data['status'], 'pending')

        # Customer cannot approve own request
        review_url = reverse('cheque-request-review', args=[req_id])
        forbidden = self.client.patch(review_url, {'status': 'approved'})
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # Manager approves then issues
        self._authenticate('manager1')
        approve = self.client.patch(review_url, {'status': 'approved', 'remarks': 'Verified'})
        self.assertEqual(approve.status_code, status.HTTP_200_OK)
        self.assertEqual(approve.data['status'], 'approved')

        issue = self.client.patch(review_url, {'status': 'issued'})
        self.assertEqual(issue.status_code, status.HTTP_200_OK)
        self.assertEqual(issue.data['status'], 'issued')

    def test_separation_of_duties_prevents_self_cheque_approval(self):
        superadmin = CustomUser.objects.get(username='superadmin')
        self._authenticate('superadmin')
        self.client.post(
            reverse('user-open-account', args=[superadmin.id]),
            {'account_type': 'current', 'initial_balance': '500.00'},
        )
        req_resp = self.client.post(self.create_url, {'leaves_requested': 10})
        self.assertEqual(req_resp.status_code, status.HTTP_201_CREATED)

        review_url = reverse('cheque-request-review', args=[req_resp.data['id']])
        self_approve = self.client.patch(review_url, {'status': 'approved'})
        self.assertEqual(self_approve.status_code, status.HTTP_400_BAD_REQUEST)

        # Another manager can still review it
        self._authenticate('manager1')
        mgr_approve = self.client.patch(review_url, {'status': 'approved'})
        self.assertEqual(mgr_approve.status_code, status.HTTP_200_OK)

