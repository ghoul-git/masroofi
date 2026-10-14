import json

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from expenses.middleware import remember_consent
from expenses.services import account_service, consent_service


def consents_from_post(post) -> dict:
    """{field name: True if the box was ticked} for the three consent checkboxes."""
    return {key: post.get(key) == "on" for key in consent_service.REQUIRED_CONSENTS}


def _safe_next(request, default="home"):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                   require_https=request.is_secure()):
        return target
    return default


@login_required
def consent_page(request):
    """Shown to existing users until they accept the current Terms and Privacy Policy versions."""
    if request.method == "POST":
        try:
            consent_service.accept(request.user, consents_from_post(request.POST))
        except ValidationError as e:
            return render(request, "expenses/consent.html", {"errors": e.messages, "next": _safe_next(request, "")})
        remember_consent(request)
        return redirect(_safe_next(request))
    return render(request, "expenses/consent.html", {"next": _safe_next(request, "")})


def _render_account(request, delete_errors=None, status=200):
    return render(request, "expenses/account.html", {
        "latest_consent": consent_service.latest(request.user),
        "delete_errors": delete_errors,
    }, status=status)


@login_required
def account_page(request):
    return _render_account(request)


@login_required
def export_data(request):
    data = account_service.export_user_data(request.user)
    filename = f"masroofi-data-{request.user.username}-{timezone.localdate().isoformat()}.json"
    response = HttpResponse(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def withdraw_consent(request):
    return render(request, "expenses/withdraw_consent.html")


@login_required
@require_POST
def delete_account(request):
    try:
        account_service.delete_account(request.user, request.POST.get("password", ""))
    except ValidationError as e:
        # Show the error on the page the form was submitted from.
        if request.POST.get("from") == "withdraw":
            return render(request, "expenses/withdraw_consent.html", {"delete_errors": e.messages}, status=400)
        return _render_account(request, delete_errors=e.messages, status=400)
    logout(request)
    return redirect("account-deleted")


def account_deleted(request):
    return render(request, "expenses/account_deleted.html")
