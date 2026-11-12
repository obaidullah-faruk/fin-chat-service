from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AgentChatView, ChatMessageListCreateView, ChatSessionViewSet

router = DefaultRouter()
router.register('sessions', ChatSessionViewSet, basename='chat-session')

urlpatterns = [
    path(
        'sessions/<int:session_id>/messages/',
        ChatMessageListCreateView.as_view(),
        name='chat-session-messages',
    ),
    path(
        'sessions/<int:session_id>/agent/',
        AgentChatView.as_view(),
        name='chat-session-agent',
    ),
    path('', include(router.urls)),
]

