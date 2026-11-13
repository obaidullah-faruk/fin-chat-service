import logging

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChatMessage, ChatSession
from .serializers import (
    ChatExchangeResponseSerializer,
    ChatMessageCreateSerializer,
    ChatMessageSerializer,
    ChatSessionSerializer,
)

logger = logging.getLogger('finchat.chat')


class AIServiceUnavailableError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'AI service is temporarily unavailable.'
    default_code = 'ai_service_unavailable'


def _generate_placeholder_reply(user, content: str) -> str:
    """Temporary echo/placeholder responder until the LLM + MCP agent is wired up."""
    account = getattr(user, 'bank_account', None)
    lowered = content.lower()
    if 'balance' in lowered and account:
        return (
            f'[Placeholder Assistant] Your current {account.account_type} account '
            f'({account.account_number}) balance is {account.currency} {account.balance}. '
            f'Full AI agent capabilities will be available later.'
        )
    return (
        f'[Placeholder Assistant] Received: "{content}". '
        f'The AI agent and MCP server integration will be connected later.'
    )


class ChatSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ChatSessionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ChatSession.objects.none()
        return ChatSession.objects.filter(user=self.request.user).prefetch_related('messages')

    def perform_create(self, serializer):
        session = serializer.save(user=self.request.user)
        logger.info(
            'Chat session created',
            extra={'user_id': self.request.user.id, 'session_id': session.id},
        )

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        session = self.get_object()
        if session.status == ChatSession.Status.CLOSED:
            return Response(ChatSessionSerializer(session).data)
        session.status = ChatSession.Status.CLOSED
        session.closed_at = timezone.now()
        session.save(update_fields=['status', 'closed_at', 'updated_at'])
        logger.info(
            'Chat session closed',
            extra={'user_id': request.user.id, 'session_id': session.id},
        )
        return Response(ChatSessionSerializer(session).data)


class ChatMessageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_session(self, user, session_id: int) -> ChatSession:
        try:
            return ChatSession.objects.get(pk=session_id, user=user)
        except ChatSession.DoesNotExist as exc:
            raise NotFound('Chat session not found.') from exc

    @extend_schema(responses=ChatMessageSerializer(many=True))
    def get(self, request, session_id: int):
        session = self._get_session(request.user, session_id)
        messages = session.messages.all()
        return Response(ChatMessageSerializer(messages, many=True).data)

    @extend_schema(request=ChatMessageCreateSerializer, responses=ChatMessageSerializer)
    @transaction.atomic
    def post(self, request, session_id: int):
        session = self._get_session(request.user, session_id)
        if session.status == ChatSession.Status.CLOSED:
            return Response(
                {'detail': 'This chat session is closed. No new messages can be added.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ChatMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = serializer.validated_data['content'].strip()

        user_msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.USER,
            content=content,
        )

        reply_text = _generate_placeholder_reply(request.user, content)
        assistant_msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=reply_text,
            metadata={'mode': 'placeholder_echo', 'agent_ready': True},
        )

        if not session.title:
            session.title = content[:60]
        session.save(update_fields=['title', 'updated_at'])

        logger.info(
            'Chat message exchanged',
            extra={'user_id': request.user.id, 'session_id': session.id},
        )
        return Response(
            {
                'user_message': ChatMessageSerializer(user_msg).data,
                'assistant_message': ChatMessageSerializer(assistant_msg).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AgentChatView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_session(self, user, session_id: int) -> ChatSession:
        try:
            return ChatSession.objects.get(pk=session_id, user=user)
        except ChatSession.DoesNotExist as exc:
            raise NotFound('Chat session not found.') from exc

    def _call_ai_service(self, user, session: ChatSession, message: str) -> dict:
        account = getattr(user, 'bank_account', None)
        recent_msgs = list(session.messages.order_by('-created_at', '-id')[:10])
        recent_msgs.reverse()
        history = [{'role': m.role, 'content': m.content} for m in recent_msgs]

        payload = {
            'user_id': user.id,
            'role': user.role.name,
            'account_number': account.account_number if account else None,
            'session_id': session.id,
            'message': message,
            'history': history,
        }
        headers = {'X-Internal-Key': settings.INTERNAL_API_KEY}
        url = f"{settings.AI_SERVICE_URL.rstrip('/')}/chat/process"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get('reply'), str):
                    raise ValueError('Invalid AI service response format.')
                return data
        except (httpx.HTTPError, ValueError) as exc:
            logger.error(
                'AI service request failed',
                extra={'user_id': user.id, 'session_id': session.id, 'error': str(exc)},
            )
            raise AIServiceUnavailableError() from exc

    @extend_schema(request=ChatMessageCreateSerializer, responses={201: ChatExchangeResponseSerializer})
    @transaction.atomic
    def post(self, request, session_id: int):
        session = self._get_session(request.user, session_id)
        if session.status == ChatSession.Status.CLOSED:
            return Response(
                {'detail': 'This chat session is closed. No new messages can be added.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ChatMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = serializer.validated_data['content'].strip()

        ai_data = self._call_ai_service(request.user, session, content)
        reply_text = ai_data['reply']
        tools_called = ai_data.get('tools_called', [])

        user_msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.USER,
            content=content,
        )
        assistant_msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=reply_text,
            metadata={'mode': 'ai_service', 'tools_called': tools_called},
        )

        if not session.title:
            session.title = content[:60]
        session.save(update_fields=['title', 'updated_at'])

        logger.info(
            'Agent chat message processed',
            extra={'user_id': request.user.id, 'session_id': session.id},
        )
        return Response(
            {
                'user_message': ChatMessageSerializer(user_msg).data,
                'assistant_message': ChatMessageSerializer(assistant_msg).data,
            },
            status=status.HTTP_201_CREATED,
        )

