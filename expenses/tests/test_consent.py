from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from expenses.models import ConsentRecord
from expenses.services import consent_service, user_service
from expenses.tests.factories import ALL_CONSENTS, PASSWORD, make_user

User = get_user_model()

FORM = {"username": "newuser", "email": "new@example.com", "password": "a-strong-pass-123"}
TICKED = {"accept_terms": "on", "accept_privacy": "on", "confirm_age": "on"}


class RegistrationConsentTests(TestCase):
    def test_register_page_has_three_unticked_required_boxes_with_links(self):
        html = self.client.get("/register/").content.decode()
        for name in TICKED:
            self.assertIn(f'name="{name}" required>', html)  # no "checked"
        self.assertIn("I agree to the <a href=\"/terms/\"", html)
        self.assertIn("including sending\n            receipt text to an AI provider outside Jordan", html)
        self.assertIn('href="/privacy/"', html)
        self.assertIn("I am 18 years or older", html)

    def test_registration_fails_without_each_box(self):
        for missing, message in consent_service.REQUIRED_CONSENTS.items():
            with self.subTest(missing=missing):
                boxes = {k: v for k, v in TICKED.items() if k != missing}
                response = self.client.post("/register/", {**FORM, **boxes})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertFalse(User.objects.filter(username="newuser").exists())
        self.assertFalse(ConsentRecord.objects.exists())

    def test_registration_fails_with_no_boxes(self):
        response = self.client.post("/register/", FORM)
        for message in consent_service.REQUIRED_CONSENTS.values():
            self.assertContains(response, message)
        self.assertFalse(User.objects.exists())

    def test_ticked_boxes_stay_ticked_when_another_field_is_wrong(self):
        response = self.client.post("/register/", {**FORM, "email": "not-an-email", **TICKED})
        self.assertContains(response, 'name="accept_terms" required checked')

    @override_settings(TERMS_VERSION="2.1", PRIVACY_VERSION="1.4")
    def test_registration_creates_a_consent_record_for_the_current_versions(self):
        response = self.client.post("/register/", {**FORM, **TICKED})
        self.assertRedirects(response, "/")
        user = User.objects.get(username="newuser")
        record = ConsentRecord.objects.get(user=user)
        self.assertEqual((record.terms_version, record.privacy_version), ("2.1", "1.4"))
        self.assertIsNotNone(record.accepted_at)
        self.assertEqual(self.client.get("/").status_code, 200)  # not sent to /consent/

    def test_service_requires_every_consent(self):
        with self.assertRaises(ValidationError) as ctx:
            user_service.register_user("x", "", "a-strong-pass-123", {"accept_terms": True})
        self.assertEqual(len(ctx.exception.messages), 2)
        # "on" strings are not enough: the view must turn them into True.
        with self.assertRaises(ValidationError):
            user_service.register_user("x", "", "a-strong-pass-123", {k: "on" for k in ALL_CONSENTS})
        self.assertFalse(User.objects.exists())

    def test_default_versions_are_1_0(self):
        self.assertEqual(consent_service.current_versions(), ("1.0", "1.0"))


class ConsentRedirectTests(TestCase):
    def setUp(self):
        self.user = make_user("olduser", consent=False)
        self.client.force_login(self.user)

    def test_pages_redirect_to_consent_with_next(self):
        for url in ["/", "/upload/", "/expenses/", "/chat/"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f"/consent/?next={url.replace('/', '%2F')}", fetch_redirect_response=False)

    def test_api_returns_403_json_instead_of_a_redirect(self):
        response = self.client.get("/api/expenses/")
        self.assertEqual(response.status_code, 403)
        self.assertIn("accept the current Terms of Service", response.json()["detail"])

    def test_exempt_urls_are_not_redirected(self):
        for url in ["/consent/", "/terms/", "/privacy/", "/account/", "/account/export/", "/account/withdraw/",
                    "/static/expenses/css/main.css"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotIn("/consent/", response.get("Location", ""))
        # Admin is exempt too: a non-staff user gets the admin login page, not the consent page.
        self.assertTrue(self.client.get("/admin/")["Location"].startswith("/admin/login/"))
        self.assertEqual(self.client.post("/logout/").status_code, 302)

    def test_login_leads_to_the_consent_page(self):
        self.client.logout()
        response = self.client.post("/login/", {"username": "olduser", "password": PASSWORD}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], "/consent/?next=%2F")
        self.assertContains(response, "Please review and accept")

    def test_accepting_records_consent_and_returns_to_next(self):
        response = self.client.post("/consent/", {**TICKED, "next": "/expenses/"})
        self.assertRedirects(response, "/expenses/")
        self.assertTrue(consent_service.has_current_consent(self.user))
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_accepting_needs_every_box(self):
        response = self.client.post("/consent/", {"accept_terms": "on", "accept_privacy": "on", "next": "/"})
        self.assertContains(response, "Please confirm that you are 18 years or older.")
        self.assertFalse(ConsentRecord.objects.exists())
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_next_to_another_site_is_ignored(self):
        response = self.client.post("/consent/", {**TICKED, "next": "https://evil.example.com/"})
        self.assertRedirects(response, "/")

    def test_new_version_asks_users_to_accept_again(self):
        ConsentRecord.objects.create(user=self.user, terms_version="1.0", privacy_version="1.0")
        self.assertEqual(self.client.get("/").status_code, 200)  # also caches 1.0/1.0 in the session
        with override_settings(PRIVACY_VERSION="2.0"):
            response = self.client.get("/")
            self.assertRedirects(response, "/consent/?next=%2F", fetch_redirect_response=False)
            self.client.post("/consent/", {**TICKED, "next": "/"})
            self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(
            list(ConsentRecord.objects.filter(user=self.user).values_list("privacy_version", flat=True)),
            ["1.0", "2.0"],
        )

    def test_logged_out_visitors_are_not_affected(self):
        self.client.logout()
        self.assertEqual(self.client.get("/register/").status_code, 200)


class LegalPagesTests(TestCase):
    def test_terms_and_privacy_are_public_placeholders(self):
        for url, title in [("/terms/", "Terms of Service"), ("/privacy/", "Privacy Policy")]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, f"<h1>{title}</h1>")
                self.assertContains(response, "Content coming soon")
                self.assertContains(response, 'class="navbar"')

    def test_footer_links_on_every_page(self):
        self.client.force_login(make_user())
        for url in ["/login/", "/register/", "/", "/upload/", "/expenses/", "/chat/", "/account/", "/no-such-page/"]:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertIn('<footer class="site-footer">', html)
                self.assertIn('href="/terms/"', html)
                self.assertIn('href="/privacy/"', html)

    def test_account_link_in_navbar(self):
        self.client.force_login(make_user())
        self.assertContains(self.client.get("/"), '<a href="/account/">Account</a>')
