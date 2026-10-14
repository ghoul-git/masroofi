from rest_framework import serializers

from expenses.models import ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "tools_used", "created_at"]
        read_only_fields = fields


class ChatAnswerSerializer(serializers.Serializer):
    """Output of chat_service.ask."""

    answer = serializers.CharField()
    tools_used = serializers.ListField(child=serializers.DictField())
    response_time = serializers.FloatField()
    usage = serializers.DictField()
