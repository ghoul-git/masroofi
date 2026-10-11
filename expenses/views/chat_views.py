from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from expenses.serializers.chat_serializers import ChatAnswerSerializer, ChatMessageSerializer
from expenses.services import chat_service
from expenses.views.api import ServiceAPIView


class ChatView(ServiceAPIView):
    parser_classes = [JSONParser]

    def post(self, request):
        question = request.data.get("question") if isinstance(request.data, dict) else None
        result = chat_service.ask(request.user, question)
        return Response(ChatAnswerSerializer(result).data)


class ChatHistoryView(ServiceAPIView):
    def get(self, request):
        messages = chat_service.get_history(request.user)
        return Response(ChatMessageSerializer(messages, many=True).data)


@login_required
def chat_page(request):
    return render(request, "expenses/chat.html")
