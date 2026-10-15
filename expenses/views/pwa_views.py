"""The installable web app: manifest, service worker and offline page.

The service worker is served from /sw.js (not /static/) because a service worker
only controls pages under its own path, and it must control the whole site.
"""
import hashlib
import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse

# The same colours as --brand and --page-background in static/expenses/css/main.css.
THEME_COLOR = "#0f766e"
BACKGROUND_COLOR = "#f5f6f8"

ICONS = [
    {"path": "expenses/icons/icon-192.png", "sizes": "192x192", "purpose": "any"},
    {"path": "expenses/icons/icon-512.png", "sizes": "512x512", "purpose": "any"},
    {"path": "expenses/icons/icon-maskable-512.png", "sizes": "512x512", "purpose": "maskable"},
]

# Stored when the service worker installs, so the offline page can be shown without a connection.
PRECACHED_STATIC = ["expenses/css/main.css", "expenses/icons/icon-192.png"]

# Paths the service worker never caches, even if a static-looking request were made to them.
NEVER_CACHE = ["/api/", "/admin/", "/account/", "/receipts/", "/media/"]


def _static_prefix() -> str:
    return settings.STATIC_URL if settings.STATIC_URL.startswith(("/", "http")) else f"/{settings.STATIC_URL}"


def manifest(request):
    data = {
        "name": "Masroofi",
        "short_name": "Masroofi",
        "description": "Scan receipts and ask about your spending.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "theme_color": THEME_COLOR,
        "background_color": BACKGROUND_COLOR,
        "icons": [{"src": static(i["path"]), "sizes": i["sizes"], "type": "image/png", "purpose": i["purpose"]}
                  for i in ICONS],
    }
    return JsonResponse(data, content_type="application/manifest+json")


def service_worker(request):
    precache = [reverse("offline")] + [static(path) for path in PRECACHED_STATIC]
    # A new list (e.g. new hashed file names after a deploy) gives a new cache name, and the
    # browser installs the new worker because this file's bytes changed.
    version = hashlib.sha256("\n".join(precache).encode()).hexdigest()[:12]
    response = render(request, "pwa/sw.js", {
        "version": version,
        "offline_url": json.dumps(reverse("offline")),
        "precache": json.dumps(precache),
        "static_prefix": json.dumps(_static_prefix()),
        "never_cache": json.dumps(NEVER_CACHE),
    }, content_type="text/javascript")
    response["Cache-Control"] = "no-cache"  # browsers check for a new worker on every visit
    return response


def offline(request):
    """Shown by the service worker when a page cannot be loaded. It has no user data, so it can be cached."""
    return render(request, "pwa/offline.html", {"theme_color": THEME_COLOR})
