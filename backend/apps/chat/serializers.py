from rest_framework import serializers

from .models import ChatMessage, ChatSession


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'session', 'role', 'content', 'metadata', 'created_at']
        read_only_fields = ['id', 'session', 'role', 'metadata', 'created_at']


class ChatMessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(min_length=1, max_length=4000)


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = ['id', 'title', 'message_count', 'last_message', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_message_count(self, obj) -> int:
        return obj.messages.count()

    def get_last_message(self, obj) -> str | None:
        msg = obj.messages.order_by('-created_at', '-id').first()
        return msg.content[:100] if msg else None

