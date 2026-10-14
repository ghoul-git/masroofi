import json
import logging
import os
import subprocess
import sys
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from config.settings import env_bool, env_int, env_list
from expenses.tests.factories import make_user

# Printed by a fresh Python process so the settings are built from the environment we pass in.
PRINT_SETTINGS = """
import json, django
from django.conf import settings
django.setup()
print(json.dumps({
    "DEBUG": settings.DEBUG,
    "ALLOWED_HOSTS": settings.ALLOWED_HOSTS,
    "CSRF_TRUSTED_ORIGINS": settings.CSRF_TRUSTED_ORIGINS,
    "SESSION_COOKIE_SECURE": settings.SESSION_COOKIE_SECURE,
    "CSRF_COOKIE_SECURE": settings.CSRF_COOKIE_SECURE,
    "SECURE_SSL_REDIRECT": settings.SECURE_SSL_REDIRECT,
    "SECURE_HSTS_SECONDS": settings.SECURE_HSTS_SECONDS,
    "SECURE_PROXY_SSL_HEADER": settings.SECURE_PROXY_SSL_HEADER,
    "X_FRAME_OPTIONS": settings.X_FRAME_OPTIONS,
    "SECURE_CONTENT_TYPE_NOSNIFF": settings.SECURE_CONTENT_TYPE_NOSNIFF,
    "STATICFILES_BACKEND": settings.STORAGES["staticfiles"]["BACKEND"],
    "FREE_RECEIPTS_PER_MONTH": settings.FREE_RECEIPTS_PER_MONTH,
}))
"""


def run_with_env(args, **env):
    """Run a Python command in the project with these environment variables set (they win over .env)."""
    return subprocess.run(
        [sys.executable, *args],
        cwd=settings.BASE_DIR,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


PRODUCTION_ENV = {
    "DEBUG": "False",
    "ALLOWED_HOSTS": "masroofi.example.com, www.masroofi.example.com",
    "CSRF_TRUSTED_ORIGINS": "https://masroofi.example.com",
    "SECURE_SSL_REDIRECT": "",
    "SECURE_HSTS_SECONDS": "",
    "FREE_RECEIPTS_PER_MONTH": "12",
}


class ProductionSettingsTests(SimpleTestCase):
    def test_debug_false_settings_load_with_every_security_setting(self):
        result = run_with_env(["-c", PRINT_SETTINGS], **PRODUCTION_ENV)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(values, {
            "DEBUG": False,
            "ALLOWED_HOSTS": ["masroofi.example.com", "www.masroofi.example.com"],
            "CSRF_TRUSTED_ORIGINS": ["https://masroofi.example.com"],
            "SESSION_COOKIE_SECURE": True,
            "CSRF_COOKIE_SECURE": True,
            "SECURE_SSL_REDIRECT": True,
            "SECURE_HSTS_SECONDS": 3600,
            "SECURE_PROXY_SSL_HEADER": ["HTTP_X_FORWARDED_PROTO", "https"],
            "X_FRAME_OPTIONS": "DENY",
            "SECURE_CONTENT_TYPE_NOSNIFF": True,
            "STATICFILES_BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
            "FREE_RECEIPTS_PER_MONTH": 12,
        })

    def test_debug_false_passes_the_deployment_check(self):
        result = run_with_env(["manage.py", "check", "--deploy", "--fail-level", "ERROR"], **PRODUCTION_ENV)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_debug_true_keeps_development_settings(self):
        result = run_with_env(["-c", PRINT_SETTINGS], DEBUG="True", ALLOWED_HOSTS="", CSRF_TRUSTED_ORIGINS="")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(values["SESSION_COOKIE_SECURE"])
        self.assertFalse(values["SECURE_SSL_REDIRECT"])
        self.assertEqual(values["ALLOWED_HOSTS"], [])
        self.assertEqual(values["STATICFILES_BACKEND"], "django.contrib.staticfiles.storage.StaticFilesStorage")

    def test_env_helpers(self):
        with mock.patch.dict(os.environ, {"X_LIST": " a.com ,, b.com ", "X_INT": "7", "X_BOOL": "True", "X_EMPTY": ""}):
            self.assertEqual(env_list("X_LIST"), ["a.com", "b.com"])
            self.assertEqual(env_list("X_MISSING"), [])
            self.assertEqual(env_int("X_INT", 3), 7)
            self.assertEqual(env_int("X_EMPTY", 3), 3)
            self.assertTrue(env_bool("X_BOOL", False))
            self.assertTrue(env_bool("X_EMPTY", True))

    def test_whitenoise_and_static_root(self):
        middleware = settings.MIDDLEWARE
        self.assertEqual(middleware.index("whitenoise.middleware.WhiteNoiseMiddleware"),
                         middleware.index("django.middleware.security.SecurityMiddleware") + 1)
        self.assertEqual(settings.STATIC_ROOT, settings.BASE_DIR / "staticfiles")

    def test_logging_writes_errors_to_the_console_with_a_timestamp(self):
        handler = settings.LOGGING["handlers"]["console"]
        self.assertEqual((handler["class"], handler["level"]), ("logging.StreamHandler", "ERROR"))
        fmt = settings.LOGGING["formatters"][handler["formatter"]]
        line = logging.Formatter(fmt["format"], style=fmt["style"]).format(
            logging.LogRecord("expenses", logging.ERROR, __file__, 1, "Boom", None, None)
        )
        self.assertRegex(line, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ERROR expenses: Boom$")


class ErrorPageTests(TestCase):
    # Tests run with DEBUG=False, so these are the pages real users see.

    def test_404_uses_the_site_layout_and_no_technical_details(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        html = response.content.decode()
        self.assertIn("Page not found", html)
        self.assertIn('class="navbar"', html)
        for detail in ["Traceback", "URLconf", "no-such-page", "Request Method"]:
            self.assertNotIn(detail, html)

    def test_500_uses_the_site_layout_and_no_technical_details(self):
        self.client.force_login(make_user())
        self.client.raise_request_exception = False
        with mock.patch("expenses.views.auth_views.render", side_effect=RuntimeError("secret internal detail")), \
                self.assertLogs("django.request", "ERROR"):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 500)
        html = response.content.decode()
        self.assertIn("Something went wrong", html)
        self.assertIn('class="navbar"', html)
        for detail in ["Traceback", "RuntimeError", "secret internal detail"]:
            self.assertNotIn(detail, html)
