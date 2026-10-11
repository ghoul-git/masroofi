from django.contrib.auth import views as auth_views
from django.urls import path

from expenses.views import auth_views as app_auth
from expenses.views import chat_views, expense_views, receipt_views

urlpatterns = [
    path("", app_auth.home, name="home"),
    path("register/", app_auth.register, name="register"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("upload/", receipt_views.upload_page, name="upload"),
    path("expenses/", expense_views.expenses_page, name="expenses"),
    path("chat/", chat_views.chat_page, name="chat"),
    path("api/receipts/", receipt_views.ReceiptUploadView.as_view(), name="api-receipt-upload"),
    path("api/receipts/<int:receipt_id>/confirm/", receipt_views.ReceiptConfirmView.as_view(), name="api-receipt-confirm"),
    path("api/expenses/", expense_views.ExpenseListView.as_view(), name="api-expense-list"),
    path("api/expenses/<int:expense_id>/", expense_views.ExpenseDetailView.as_view(), name="api-expense-detail"),
    path("api/chat/", chat_views.ChatView.as_view(), name="api-chat"),
    path("api/chat/history/", chat_views.ChatHistoryView.as_view(), name="api-chat-history"),
]
