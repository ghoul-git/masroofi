from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from expenses.middleware import remember_consent
from expenses.services import user_service
from expenses.views.account_views import consents_from_post


def register(request):
    if request.method == "POST":
        try:
            user = user_service.register_user(
                request.POST.get("username", "").strip(),
                request.POST.get("email", "").strip(),
                request.POST.get("password", ""),
                consents_from_post(request.POST),
            )
        except ValidationError as e:
            return render(request, "expenses/register.html", {"errors": e.messages})
        login(request, user)
        remember_consent(request)
        return redirect("home")
    return render(request, "expenses/register.html")


@login_required
def home(request):
    return render(request, "expenses/home.html")
