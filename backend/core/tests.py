from django.core.management import call_command
from django.test import override_settings
from django.urls import path
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from apps.accounts.models import CustomUser
from core.internal_auth import HasInternalAPIKey, get_internal_user


class _DummyInternalView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalAPIKey]

    def get(self, request):
        user = get_internal_user(request)
        return Response({'user_id': user.id, 'username': user.username})


urlpatterns = [
    path('internal-test/', _DummyInternalView.as_view(), name='dummy-internal'),
]


@override_settings(ROOT_URLCONF=__name__, INTERNAL_API_KEY='test-internal-secret')
class InternalAuthTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.customer = CustomUser.objects.get(username='customer1')
        self.url = '/internal-test/'

    def test_missing_internal_key_returns_403(self):
        resp = self.client.get(self.url, HTTP_X_USER_ID=str(self.customer.id))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_wrong_internal_key_returns_403(self):
        resp = self.client.get(
            self.url,
            HTTP_X_INTERNAL_KEY='wrong-key',
            HTTP_X_USER_ID=str(self.customer.id),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(INTERNAL_API_KEY='')
    def test_empty_configured_internal_key_returns_403(self):
        resp = self.client.get(
            self.url,
            HTTP_X_INTERNAL_KEY='',
            HTTP_X_USER_ID=str(self.customer.id),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_valid_key_and_user_id_resolves_user_without_jwt(self):
        resp = self.client.get(
            self.url,
            HTTP_X_INTERNAL_KEY='test-internal-secret',
            HTTP_X_USER_ID=str(self.customer.id),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp.data,
            {'user_id': self.customer.id, 'username': 'customer1'},
        )

    def test_missing_user_id_header_returns_400(self):
        resp = self.client.get(
            self.url,
            HTTP_X_INTERNAL_KEY='test-internal-secret',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['detail'], 'Missing X-User-Id header.')

    def test_invalid_user_id_header_returns_400(self):
        for bad_value in ('abc', '0', '-5', '12.5', '   '):
            resp = self.client.get(
                self.url,
                HTTP_X_INTERNAL_KEY='test-internal-secret',
                HTTP_X_USER_ID=bad_value,
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_user_id_returns_404(self):
        resp = self.client.get(
            self.url,
            HTTP_X_INTERNAL_KEY='test-internal-secret',
            HTTP_X_USER_ID='999999',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_user_returns_404(self):
        self.customer.is_active = False
        self.customer.save(update_fields=['is_active'])

        resp = self.client.get(
            self.url,
            HTTP_X_INTERNAL_KEY='test-internal-secret',
            HTTP_X_USER_ID=str(self.customer.id),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

