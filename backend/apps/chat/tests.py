from unittest.mock import Mock, patch

import httpx
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ChatMessage


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

    @override_settings(
        INTERNAL_API_KEY='test-internal-key',
        AI_SERVICE_URL='http://ai-service:8001',
    )
    @patch('apps.chat.views.httpx.Client')
    def test_agent_chat_calls_ai_service_and_persists_messages(self, mock_client_cls):
        self._authenticate('customer1')
        session_resp = self.client.post(self.sessions_url, {})
        session_id = session_resp.data['id']

        mock_response = Mock()
        mock_response.json.return_value = {
            'reply': '[AI Service Echo] Received: "Hello agent"',
            'tools_called': [],
        }
        mock_response.raise_for_status.return_value = None
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_response

        agent_url = reverse('chat-session-agent', args=[session_id])
        resp = self.client.post(agent_url, {'content': 'Hello agent'})

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['user_message']['content'], 'Hello agent')
        self.assertEqual(
            resp.data['assistant_message']['content'],
            '[AI Service Echo] Received: "Hello agent"',
        )
        self.assertEqual(ChatMessage.objects.filter(session_id=session_id).count(), 2)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        self.assertEqual(call_args.args[0], 'http://ai-service:8001/chat/process')
        self.assertEqual(call_args.kwargs['headers'], {'X-Internal-Key': 'test-internal-key'})
        self.assertEqual(call_args.kwargs['json']['role'], 'customer')
        self.assertEqual(call_args.kwargs['json']['account_number'], 'FC1000000001')
        self.assertEqual(call_args.kwargs['json']['session_id'], session_id)
        self.assertEqual(call_args.kwargs['json']['message'], 'Hello agent')

    @override_settings(
        INTERNAL_API_KEY='test-internal-key',
        AI_SERVICE_URL='http://ai-service:8001',
    )
    @patch('apps.chat.views.httpx.Client')
    def test_agent_chat_handles_ai_service_failure(self, mock_client_cls):
        self._authenticate('customer1')
        session_resp = self.client.post(self.sessions_url, {})
        session_id = session_resp.data['id']

        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.side_effect = httpx.ConnectError('connection refused')

        agent_url = reverse('chat-session-agent', args=[session_id])
        resp = self.client.post(agent_url, {'content': 'Hello agent'})

        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(ChatMessage.objects.filter(session_id=session_id).count(), 0)

    def test_agent_chat_rejects_other_users_session(self):
        self._authenticate('customer1')
        session_id = self.client.post(self.sessions_url, {}).data['id']

        self._authenticate('customer2')
        agent_url = reverse('chat-session-agent', args=[session_id])
        resp = self.client.post(agent_url, {'content': 'Unauthorized'})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class WebSocketChatTests(APITestCase):
    def setUp(self):
        call_command('seed_users')
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import AccessToken
        from apps.chat.models import ChatSession

        User = get_user_model()
        self.customer1 = User.objects.get(username='customer1')
        self.customer2 = User.objects.get(username='customer2')
        self.token1 = str(AccessToken.for_user(self.customer1))
        self.session1 = ChatSession.objects.create(user=self.customer1, title='Test Session')

    def test_path_regex_matching(self):
        from apps.chat.websocket import WS_PATH_REGEX
        m1 = WS_PATH_REGEX.match('/ws/chat/1/')
        self.assertIsNotNone(m1)
        self.assertEqual(m1.group('session_id'), '1')

        m2 = WS_PATH_REGEX.match('/ws/chat/42')
        self.assertIsNotNone(m2)
        self.assertEqual(m2.group('session_id'), '42')

        self.assertIsNone(WS_PATH_REGEX.match('/ws/chat/abc/'))
        self.assertIsNone(WS_PATH_REGEX.match('/api/v1/chat/'))

    async def test_websocket_rejects_missing_token(self):
        from apps.chat.websocket import chat_websocket_application

        scope = {
            'type': 'websocket',
            'path': f'/ws/chat/{self.session1.id}/',
            'query_string': b'',
        }
        sent_events = []

        async def fake_send(ev):
            sent_events.append(ev)

        async def fake_receive():
            return {'type': 'websocket.disconnect'}

        await chat_websocket_application(scope, fake_receive, fake_send)
        self.assertEqual(len(sent_events), 1)
        self.assertEqual(sent_events[0]['type'], 'websocket.close')
        self.assertEqual(sent_events[0]['code'], 4001)

    async def test_websocket_rejects_invalid_token(self):
        from apps.chat.websocket import chat_websocket_application

        scope = {
            'type': 'websocket',
            'path': f'/ws/chat/{self.session1.id}/',
            'query_string': b'token=invalid_expired_token',
        }
        sent_events = []

        async def fake_send(ev):
            sent_events.append(ev)

        async def fake_receive():
            return {'type': 'websocket.disconnect'}

        await chat_websocket_application(scope, fake_receive, fake_send)
        self.assertEqual(len(sent_events), 1)
        self.assertEqual(sent_events[0]['type'], 'websocket.close')
        self.assertEqual(sent_events[0]['code'], 4001)

    async def test_websocket_rejects_other_user_session(self):
        from apps.chat.websocket import chat_websocket_application
        from rest_framework_simplejwt.tokens import AccessToken

        token2 = str(AccessToken.for_user(self.customer2))
        scope = {
            'type': 'websocket',
            'path': f'/ws/chat/{self.session1.id}/',
            'query_string': f'token={token2}'.encode('utf-8'),
        }
        sent_events = []

        async def fake_send(ev):
            sent_events.append(ev)

        async def fake_receive():
            return {'type': 'websocket.disconnect'}

        await chat_websocket_application(scope, fake_receive, fake_send)
        self.assertEqual(len(sent_events), 1)
        self.assertEqual(sent_events[0]['type'], 'websocket.close')
        self.assertEqual(sent_events[0]['code'], 4004)


