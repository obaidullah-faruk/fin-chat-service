from datetime import date
from decimal import Decimal
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import ActivityLog, Address, CustomUser, Role, UserProfile
from apps.banking.models import BankAccount


class AccountsAndRBACTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.login_url = reverse('auth-login')
        self.me_url = reverse('auth-me')
        self.users_url = reverse('user-list')
        self.addresses_url = reverse('address-list')

    def _authenticate(self, username: str):
        resp = self.client.post(self.login_url, {'username': username, 'password': 'Test@1234'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        return resp.data

    def test_seed_users_idempotent(self):
        initial_count = CustomUser.objects.count()
        self.assertEqual(initial_count, 6)
        call_command('seed_users')
        self.assertEqual(CustomUser.objects.count(), initial_count)

    def test_login_with_email_and_logout(self):
        resp = self.client.post(
            self.login_url, {'username': 'customer1@finchat.local', 'password': 'Test@1234'}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        logout_resp = self.client.post(
            reverse('auth-logout'), {'refresh': resp.data['refresh']}
        )
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

    def test_rbac_user_management_permissions(self):
        # Customer cannot list users
        self._authenticate('customer1')
        resp = self.client.get(self.users_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Manager cannot list users
        self._authenticate('manager1')
        resp = self.client.get(self.users_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Admin can create customer, cannot create superadmin
        self._authenticate('admin1')
        create_cust = self.client.post(
            self.users_url,
            {
                'username': 'newcust',
                'email': 'newcust@finchat.local',
                'password': 'Password123!',
                'role': 'customer',
                'initial_balance': '150.00',
            },
        )
        self.assertEqual(create_cust.status_code, status.HTTP_201_CREATED)
        self.assertTrue(BankAccount.objects.filter(user__username='newcust', balance=Decimal('150.00')).exists())

        create_sa = self.client.post(
            self.users_url,
            {
                'username': 'bad_sa',
                'email': 'bad@finchat.local',
                'password': 'Password123!',
                'role': 'superadmin',
            },
        )
        self.assertEqual(create_sa.status_code, status.HTTP_400_BAD_REQUEST)

        # Superadmin can list all users
        self._authenticate('superadmin')
        list_resp = self.client.get(self.users_url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(list_resp.data['count'], 7)

    def test_address_crud_and_primary_toggle(self):
        self._authenticate('customer1')
        resp1 = self.client.post(
            self.addresses_url,
            {
                'label': 'work',
                'street': '100 Motijheel',
                'city': 'Dhaka',
                'state': 'Dhaka',
                'postal_code': '1000',
                'country': 'Bangladesh',
                'is_primary': True,
            },
        )
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        customer1 = CustomUser.objects.get(username='customer1')
        primaries = Address.objects.filter(user=customer1, is_primary=True)
        self.assertEqual(primaries.count(), 1)
        self.assertEqual(primaries.first().id, resp1.data['id'])

    def test_activity_logs_tracking_and_visibility(self):
        self._authenticate('customer1')
        self.client.patch(self.me_url, {'phone': '+8801711111111'})

        self._authenticate('customer2')
        c2_logs = self.client.get(reverse('activity-list'))
        self.assertEqual(c2_logs.status_code, status.HTTP_200_OK)
        self.assertTrue(
            all(item['subject_username'] == 'customer2' for item in c2_logs.data['results'])
        )

        self._authenticate('manager1')
        all_logs = self.client.get(reverse('activity-list'))
        self.assertEqual(all_logs.status_code, status.HTTP_200_OK)
        self.assertTrue(
            any(
                item['subject_username'] == 'customer1' and item['action'] == 'PROFILE_UPDATED'
                for item in all_logs.data['results']
            )
        )
        self.assertTrue(
            ActivityLog.objects.filter(subject_user__username='customer1', action='LOGIN').exists()
        )

    def test_superadmin_can_open_personal_bank_account(self):
        superadmin = CustomUser.objects.get(username='superadmin')
        open_url = reverse('user-open-account', args=[superadmin.id])

        # Customer forbidden
        self._authenticate('customer1')
        self.assertEqual(
            self.client.post(open_url, {'account_type': 'current'}).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Superadmin opens personal bank account
        self._authenticate('superadmin')
        resp = self.client.post(
            open_url, {'account_type': 'current', 'initial_balance': '1250.00'}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(resp.data['bank_account'])
        self.assertEqual(Decimal(resp.data['bank_account']['balance']), Decimal('1250.00'))

        # Duplicate personal bank account rejected (one account per user)
        dup = self.client.post(open_url, {'account_type': 'savings'})
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_without_access_token_and_account_switch_no_cache(self):
        c1_login = self.client.post(
            self.login_url, {'username': 'customer1', 'password': 'Test@1234'}
        )
        self.assertEqual(c1_login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {c1_login.data['access']}")
        me1 = self.client.get(self.me_url)
        self.assertEqual(me1.status_code, status.HTTP_200_OK)
        self.assertEqual(me1.data['username'], 'customer1')
        self.assertIn('no-store', me1['Cache-Control'])
        self.assertIn('Authorization', me1['Vary'])

        # Logout succeeds even if access token is omitted/expired as long as refresh is valid
        self.client.credentials()
        logout_resp = self.client.post(
            reverse('auth-logout'), {'refresh': c1_login.data['refresh']}
        )
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

        # Blacklisted refresh token cannot be used to refresh
        refresh_resp = self.client.post(
            reverse('auth-token-refresh'), {'refresh': c1_login.data['refresh']}
        )
        self.assertEqual(refresh_resp.status_code, status.HTTP_401_UNAUTHORIZED)

        # Re-login as another user returns strictly new user data
        c2_login = self.client.post(
            self.login_url, {'username': 'customer2', 'password': 'Test@1234'}
        )
        self.assertEqual(c2_login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {c2_login.data['access']}")
        me2 = self.client.get(self.me_url)
        self.assertEqual(me2.status_code, status.HTTP_200_OK)
        self.assertEqual(me2.data['username'], 'customer2')
        self.assertNotEqual(me2.data['id'], me1.data['id'])


@override_settings(INTERNAL_API_KEY='test-internal-secret')
class InternalServiceAccountTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.customer1 = CustomUser.objects.get(username='customer1')
        self.address_url = reverse('internal-service-address')
        self.kyc_url = reverse('internal-service-kyc-status')
        self.valid_headers = {
            'HTTP_X_INTERNAL_KEY': 'test-internal-secret',
            'HTTP_X_USER_ID': str(self.customer1.id),
        }

    def test_service_endpoints_require_internal_key(self):
        self.assertEqual(
            self.client.get(
                self.kyc_url,
                HTTP_X_USER_ID=str(self.customer1.id),
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(
                self.address_url,
                {
                    'street': '10 Lake Road',
                    'city': 'Dhaka',
                    'state': 'Dhaka',
                    'postal_code': '1212',
                    'country': 'Bangladesh',
                },
                format='json',
                HTTP_X_INTERNAL_KEY='wrong-key',
                HTTP_X_USER_ID=str(self.customer1.id),
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_internal_address_updates_primary_and_creates_secondary(self):
        # Seeded customer1 already has a primary address -> updates in place (200)
        update_resp = self.client.post(
            self.address_url,
            {
                'label': 'home',
                'street': '99 Kemal Ataturk Ave',
                'city': 'Dhaka',
                'state': 'Dhaka',
                'postal_code': '1213',
                'country': 'Bangladesh',
                'is_primary': True,
            },
            format='json',
            **self.valid_headers,
        )
        self.assertEqual(update_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(update_resp.data['street'], '99 Kemal Ataturk Ave')
        self.assertEqual(Address.objects.filter(user=self.customer1).count(), 1)
        self.assertTrue(
            ActivityLog.objects.filter(
                subject_user=self.customer1,
                category=ActivityLog.Category.PROFILE,
                action='ADDRESS_UPDATED',
            ).exists()
        )

        # Adding non-primary address creates a second record (201)
        create_resp = self.client.post(
            self.address_url,
            {
                'label': 'work',
                'street': '12 Motijheel C/A',
                'city': 'Dhaka',
                'state': 'Dhaka',
                'postal_code': '1000',
                'country': 'Bangladesh',
                'is_primary': False,
            },
            format='json',
            **self.valid_headers,
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Address.objects.filter(user=self.customer1).count(), 2)

        # Missing required fields -> 400; non-owned address_id -> 404
        self.assertEqual(
            self.client.post(
                self.address_url,
                {'street': 'Only street'},
                format='json',
                **self.valid_headers,
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post(
                self.address_url,
                {
                    'address_id': 999999,
                    'street': '123 St',
                    'city': 'Dhaka',
                    'state': 'Dhaka',
                    'postal_code': '1000',
                    'country': 'Bangladesh',
                },
                format='json',
                **self.valid_headers,
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_internal_kyc_status_reflects_profile_completeness(self):
        # Seeded customer1 has primary address but no national_id / date_of_birth
        partial_resp = self.client.get(self.kyc_url, **self.valid_headers)
        self.assertEqual(partial_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(partial_resp.data['username'], 'customer1')
        self.assertEqual(partial_resp.data['kyc_status'], 'partial')
        self.assertTrue(partial_resp.data['has_primary_address'])
        self.assertTrue(partial_resp.data['has_bank_account'])
        self.assertFalse(partial_resp.data['has_national_id'])
        self.assertFalse(partial_resp.data['has_date_of_birth'])
        self.assertEqual(
            set(partial_resp.data['missing_fields']),
            {'national_id', 'date_of_birth'},
        )

        # Complete profile -> verified
        profile, _ = UserProfile.objects.get_or_create(user=self.customer1)
        profile.national_id = '1990123456789'
        profile.date_of_birth = date(1990, 5, 15)
        profile.save()

        verified_resp = self.client.get(self.kyc_url, **self.valid_headers)
        self.assertEqual(verified_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(verified_resp.data['kyc_status'], 'verified')
        self.assertTrue(verified_resp.data['has_national_id'])
        self.assertTrue(verified_resp.data['has_date_of_birth'])
        self.assertEqual(verified_resp.data['missing_fields'], [])

