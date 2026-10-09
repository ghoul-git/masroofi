from django.contrib.auth import views as auth_views
from django.urls import path

from expenses.views import auth_views as app_auth

urlpatterns = [
    path("", app_auth.home, name="home"),
    path("register/", app_auth.register, name="register"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
