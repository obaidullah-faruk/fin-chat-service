from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatMessageListCreateView, ChatSessionViewSet

router = DefaultRouter()
router.register('sessions', ChatSessionViewSet, basename='chat-session')

urlpatterns = [
    path(
        'sessions/<int:session_id>/messages/',
        ChatMessageListCreateView.as_view(),
        name='chat-session-messages',
    ),
    path('', include(router.urls)),
]

