"""Deployment: DATABASE_URL, no media folder, the /healthz endpoint and the Docker files."""
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings

from config.database import database_from_env
from expenses.tests.factories import make_user

BASE_DIR = Path(settings.BASE_DIR)
DB_VARS = {"DB_NAME": "masroofi", "DB_USER": "app", "DB_PASSWORD": "secret"}


class DatabaseUrlTests(SimpleTestCase):
    def test_database_url_is_parsed(self):
        config = database_from_env({"DATABASE_URL": "postgres://user:p%40ss@db.example.com:6543/masroofi_prod"})
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "masroofi_prod")
        self.assertEqual(config["USER"], "user")
        self.assertEqual(config["PASSWORD"], "p@ss")  # percent-encoded characters are decoded
        self.assertEqual(config["HOST"], "db.example.com")
        self.assertEqual(config["PORT"], 6543)

    def test_postgresql_scheme_and_query_options(self):
        config = database_from_env({"DATABASE_URL": "postgresql://u:p@host/name?sslmode=require"})
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["OPTIONS"], {"sslmode": "require"})

    def test_database_url_wins_over_the_db_variables(self):
        config = database_from_env({**DB_VARS, "DATABASE_URL": "postgres://u:p@url-host:5432/from_url"})
        self.assertEqual((config["NAME"], config["HOST"]), ("from_url", "url-host"))

    def test_falls_back_to_the_db_variables(self):
        for url in (None, "", "   "):
            with self.subTest(url=url):
                env = dict(DB_VARS) if url is None else {**DB_VARS, "DATABASE_URL": url}
                self.assertEqual(database_from_env(env), {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": "masroofi", "USER": "app", "PASSWORD": "secret",
                    "HOST": "localhost", "PORT": "5432",
                })

    def test_db_host_and_port_are_used_when_set(self):
        config = database_from_env({**DB_VARS, "DB_HOST": "db", "DB_PORT": "5433"})
        self.assertEqual((config["HOST"], config["PORT"]), ("db", "5433"))

    def test_missing_configuration_fails_loudly(self):
        with self.assertRaises(KeyError):
            database_from_env({"DB_USER": "app"})


class NoMediaFolderTests(SimpleTestCase):
    """Receipt images live in the database, so nothing is configured to store files on disk."""

    def test_no_media_settings(self):
        settings_source = (BASE_DIR / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertNotRegex(settings_source, r"(?m)^MEDIA_(ROOT|URL)\s*=")
        self.assertNotIn("MEDIA_ROOT", (BASE_DIR / ".env.example").read_text(encoding="utf-8"))

    def test_docker_files_have_no_media_volume(self):
        for name in ("Dockerfile", "docker-compose.yml"):
            with self.subTest(name=name):
                self.assertNotIn("media", (BASE_DIR / name).read_text(encoding="utf-8").lower())


class HealthzTests(TestCase):
    def test_ok_without_login(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("no-cache", response["Cache-Control"])

    def test_ok_for_a_logged_in_user_without_consent(self):
        self.client.force_login(make_user("bob", consent=False))
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})

    def test_checks_the_database(self):
        with mock.patch("expenses.repositories.health_repository.ping") as ping:
            self.client.get("/healthz")
        ping.assert_called_once_with()

    def test_database_down_returns_503_without_details(self):
        with mock.patch("expenses.repositories.health_repository.ping",
                        side_effect=OperationalError("could not connect to server at 10.0.0.5")), \
                self.assertLogs("expenses.services.health_service", "ERROR"),                 self.assertLogs("django.request", "ERROR"):
            response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn(b"10.0.0.5", response.content)

    def test_only_get(self):
        self.assertEqual(self.client.post("/healthz").status_code, 405)

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r"^healthz$"])
    def test_not_redirected_to_https(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/login/").status_code, 301)  # other pages still are

    def test_production_settings_exempt_it_from_the_https_redirect(self):
        settings_source = (BASE_DIR / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertIn('SECURE_REDIRECT_EXEMPT = [r"^healthz$"]', settings_source)


class DockerFilesTests(SimpleTestCase):
    """The image cannot be built in the tests; these check the parts that matter most."""

    def read(self, name):
        return (BASE_DIR / name).read_text(encoding="utf-8")

    def test_dockerignore_keeps_secrets_and_personal_data_out(self):
        ignored = {line.strip() for line in self.read(".dockerignore").splitlines()}
        for entry in (".env", ".venv", ".git", "media", "evaluation/sroie", "evaluation/receipts",
                      "evaluation/results", "**/__pycache__", "masroofi-data-*.json"):
            with self.subTest(entry=entry):
                self.assertIn(entry, ignored)

    def test_dockerfile(self):
        dockerfile = self.read("Dockerfile")
        self.assertIn("FROM python:3.11-slim", dockerfile)
        self.assertIn("libgl1 libglib2.0-0", dockerfile)
        self.assertIn("--index-url https://download.pytorch.org/whl/cpu", dockerfile)
        self.assertIn("easyocr.Reader(['ar', 'en'], gpu=False)", dockerfile)
        self.assertIn("collectstatic --noinput", dockerfile)
        self.assertIn("USER app", dockerfile)
        self.assertIn("gunicorn config.wsgi --workers 2 --timeout 60 --bind 0.0.0.0:${PORT:-8000}", dockerfile)
        # The models are downloaded as the user that runs the worker, after switching to it.
        self.assertLess(dockerfile.index("USER app"), dockerfile.index("easyocr.Reader"))

    def test_requirements_install_on_linux(self):
        requirements = self.read("requirements.txt")
        self.assertIn("--extra-index-url https://download.pytorch.org/whl/cpu", requirements)
        self.assertIn("gunicorn==", requirements)
        self.assertIn("dj-database-url==", requirements)
        for windows_only in ("pywin32", "pywinpty", "wmi==", "+cu", "win_amd64"):
            with self.subTest(package=windows_only):
                self.assertNotIn(windows_only, requirements.lower())

    def test_compose_runs_the_worker_from_the_same_image(self):
        import yaml

        services = yaml.safe_load(self.read("docker-compose.yml"))["services"]
        self.assertEqual(services["db"]["image"], "postgres:17")
        self.assertEqual(services["worker"]["command"], "python manage.py process_receipts")
        self.assertEqual(services["web"]["image"], services["worker"]["image"])
        self.assertNotIn("volumes", services["web"])  # no shared disk: images are in the database
        self.assertNotIn("volumes", services["worker"])
        self.assertEqual(services["web"]["env_file"], ".env")
