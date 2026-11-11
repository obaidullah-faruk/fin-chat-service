from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class ChatTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        self.login_url = reverse('auth-login')
        self.sessions_url = reverse('chat-session-list')

    def _authenticate(self, username: str):
        resp = self.client.post(self.login_url, {'username': username, 'password': 'Test@1234'})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_chat_session_and_echo_message(self):
        self._authenticate('customer1')
        session_resp = self.client.post(self.sessions_url, {})
        self.assertEqual(session_resp.status_code, status.HTTP_201_CREATED)
        session_id = session_resp.data['id']

        msg_url = reverse('chat-session-messages', args=[session_id])
        post_resp = self.client.post(msg_url, {'content': 'What is my balance?'})
        self.assertEqual(post_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(post_resp.data['user_message']['role'], 'user')
        self.assertEqual(post_resp.data['assistant_message']['role'], 'assistant')
        self.assertIn('FC1000000001', post_resp.data['assistant_message']['content'])

        # Another customer cannot access this session
        self._authenticate('customer2')
        self.assertEqual(self.client.get(msg_url).status_code, status.HTTP_404_NOT_FOUND)

