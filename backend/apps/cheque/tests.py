from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import ActivityLog, CustomUser
from apps.cheque.models import ChequeBookRequest


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


@override_settings(INTERNAL_API_KEY='test-internal-secret')
class InternalChequeServiceTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.customer1 = CustomUser.objects.get(username='customer1')
        self.url = reverse('internal-service-cheque-request')
        self.valid_headers = {
            'HTTP_X_INTERNAL_KEY': 'test-internal-secret',
            'HTTP_X_USER_ID': str(self.customer1.id),
        }

    def test_requires_internal_key(self):
        self.assertEqual(
            self.client.post(
                self.url,
                {'leaves_requested': 25},
                HTTP_X_USER_ID=str(self.customer1.id),
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(
                self.url,
                {'leaves_requested': 25},
                HTTP_X_INTERNAL_KEY='wrong-key',
                HTTP_X_USER_ID=str(self.customer1.id),
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_create_cheque_request_uses_primary_address_and_logs_activity(self):
        resp = self.client.post(
            self.url,
            {'leaves_requested': 50, 'remarks': 'Requested via chatbot'},
            format='json',
            **self.valid_headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['leaves_requested'], 50)
        self.assertEqual(resp.data['status'], ChequeBookRequest.Status.PENDING)
        self.assertEqual(resp.data['account_number'], 'FC1000000001')
        self.assertIn('42 Gulshan Avenue', resp.data['delivery_address_snapshot'])
        self.assertTrue(
            ActivityLog.objects.filter(
                subject_user=self.customer1,
                category=ActivityLog.Category.CHEQUE,
                action='CHEQUE_REQUESTED',
            ).exists()
        )

    def test_rejects_invalid_leaves_or_foreign_address(self):
        bad_leaves = self.client.post(
            self.url,
            {'leaves_requested': 15},
            format='json',
            **self.valid_headers,
        )
        self.assertEqual(bad_leaves.status_code, status.HTTP_400_BAD_REQUEST)

        customer2 = CustomUser.objects.get(username='customer2')
        c2_address = customer2.addresses.first()
        bad_addr = self.client.post(
            self.url,
            {'leaves_requested': 25, 'delivery_address_id': c2_address.id},
            format='json',
            **self.valid_headers,
        )
        self.assertEqual(bad_addr.status_code, status.HTTP_404_NOT_FOUND)

    def test_internal_pending_reviews_staff_only(self):
        # Create a pending cheque request
        self.client.post(
            self.url,
            {'leaves_requested': 25, 'remarks': 'Pending review test'},
            format='json',
            **self.valid_headers,
        )

        pending_url = reverse('internal-service-pending-reviews')
        manager1 = CustomUser.objects.get(username='manager1')

        # Manager can view pending items
        resp_mgr = self.client.get(
            pending_url,
            HTTP_X_INTERNAL_KEY='test-internal-secret',
            HTTP_X_USER_ID=str(manager1.id),
        )
        self.assertEqual(resp_mgr.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp_mgr.data['pending_cheques_count'], 1)

        # Customer is denied
        resp_cust = self.client.get(
            pending_url,
            HTTP_X_INTERNAL_KEY='test-internal-secret',
            HTTP_X_USER_ID=str(self.customer1.id),
        )
        self.assertEqual(resp_cust.status_code, status.HTTP_403_FORBIDDEN)

