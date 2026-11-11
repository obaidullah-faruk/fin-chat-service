import logging
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChatMessage, ChatSession
from .serializers import (
    ChatMessageCreateSerializer,
    ChatMessageSerializer,
    ChatSessionSerializer,
)

logger = logging.getLogger('finchat.chat')


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

