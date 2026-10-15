"""The installable web app: manifest, icons, service worker, offline page and small screens."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from PIL import Image

from expenses.tests.factories import make_user
from expenses.views import pwa_views

STATIC = Path(settings.BASE_DIR) / "expenses" / "static" / "expenses"
CSS = (STATIC / "css" / "main.css").read_text(encoding="utf-8")


class ManifestTests(TestCase):
    def test_manifest(self):
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        manifest = response.json()
        self.assertEqual(manifest["name"], "Masroofi")
        self.assertEqual(manifest["short_name"], "Masroofi")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual({(i["sizes"], i["purpose"]) for i in manifest["icons"]},
                         {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")})

    def test_colours_come_from_main_css(self):
        manifest = self.client.get("/manifest.webmanifest").json()
        self.assertIn(f"--brand: {manifest['theme_color']};", CSS)
        self.assertIn(f"--page-background: {manifest['background_color']};", CSS)

    def test_base_template_links_the_manifest_with_the_ios_tags(self):
        html = self.client.get("/login/").content.decode()
        self.assertIn('<link rel="manifest" href="/manifest.webmanifest">', html)
        self.assertIn(f'<meta name="theme-color" content="{pwa_views.THEME_COLOR}">', html)
        self.assertIn('<link rel="apple-touch-icon" href="/static/expenses/icons/apple-touch-icon.png">', html)
        self.assertIn('<meta name="apple-mobile-web-app-capable" content="yes">', html)
        self.assertIn('<meta name="apple-mobile-web-app-title" content="Masroofi">', html)
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1.0"', html)

    def test_icons_exist_with_the_right_sizes(self):
        for name, size in [("icon-192.png", 192), ("icon-512.png", 512), ("icon-maskable-512.png", 512),
                           ("apple-touch-icon.png", 180)]:
            with self.subTest(name=name), Image.open(STATIC / "icons" / name) as icon:
                self.assertEqual(icon.size, (size, size))

    def test_round_icons_have_transparent_corners_and_full_bleed_ones_do_not(self):
        with Image.open(STATIC / "icons" / "icon-512.png") as icon:
            self.assertEqual(icon.convert("RGBA").getpixel((0, 0))[3], 0)
        for name in ("icon-maskable-512.png", "apple-touch-icon.png"):
            with Image.open(STATIC / "icons" / name) as icon:
                self.assertEqual(icon.convert("RGBA").getpixel((0, 0))[3], 255)


class ServiceWorkerTests(TestCase):
    def setUp(self):
        self.response = self.client.get("/sw.js")
        self.js = self.response.content.decode()

    def js_constant(self, name):
        return json.loads(re.search(rf"const {name} = (.+);", self.js).group(1))

    def test_served_from_the_root_as_javascript_and_revalidated(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertEqual(self.response["Content-Type"], "text/javascript")
        self.assertEqual(self.response["Cache-Control"], "no-cache")

    def test_precaches_only_static_files_and_the_offline_page(self):
        precache = self.js_constant("PRECACHE")
        self.assertIn("/offline/", precache)
        for url in precache:
            with self.subTest(url=url):
                self.assertTrue(url == "/offline/" or url.startswith("/static/"))

    def test_never_caches_user_data(self):
        self.assertEqual(self.js_constant("STATIC_PREFIX"), "/static/")
        self.assertEqual(set(self.js_constant("NEVER_CACHE")),
                         {"/api/", "/admin/", "/account/", "/receipts/", "/media/"})
        # Pages go to the network and are never put in the cache.
        navigate = self.js[self.js.index('request.mode === "navigate"'):self.js.index("if (!isCacheable(url))")]
        self.assertNotIn("cache.put", navigate)
        self.assertEqual(self.js.count("cache.put("), 1)
        self.assertIn('!type.includes("text/html")', self.js)

    def test_cache_name_changes_with_the_precached_files(self):
        first = self.js_constant("CACHE")
        with mock.patch.object(pwa_views, "PRECACHED_STATIC", [*pwa_views.PRECACHED_STATIC, "expenses/js/api.js"]):
            other = json.loads(re.search(r"const CACHE = (.+);", self.client.get("/sw.js").content.decode()).group(1))
        self.assertTrue(first.startswith("masroofi-static-"))
        self.assertNotEqual(first, other)

    def test_is_valid_javascript(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed")
        result = subprocess.run([node, "--check", "-"], input=self.js, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)


class OfflinePageTests(TestCase):
    def test_offline_page_has_no_user_data_even_when_logged_in(self):
        user = make_user("private_username_xyz")
        self.client.force_login(user)
        html = self.client.get("/offline/").content.decode()
        self.assertIn("You're offline", html)
        self.assertNotIn("private_username_xyz", html)
        self.assertNotIn("Log out", html)
        self.assertNotIn("csrfmiddlewaretoken", html)

    def test_pwa_files_are_not_replaced_by_the_consent_page(self):
        self.client.force_login(make_user("bob", consent=False))
        self.assertEqual(self.client.get("/expenses/").status_code, 302)  # the consent redirect applies to pages
        for url in ("/sw.js", "/manifest.webmanifest", "/offline/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class SmallScreenTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())

    def test_upload_input_opens_the_camera(self):
        html = self.client.get("/upload/").content.decode()
        self.assertIn('accept="image/*" capture="environment"', html)
        self.assertIn("Reading your receipt…", html)

    def test_navbar_has_a_menu_button_and_the_site_script(self):
        html = self.client.get("/").content.decode()
        self.assertIn('id="nav-toggle" aria-expanded="false" aria-controls="nav-links"', html)
        self.assertIn('src="/static/expenses/js/site.js" data-service-worker="/sw.js"', html)

    def test_tables_stack_into_cards(self):
        for url in ("/expenses/", "/upload/"):
            with self.subTest(url=url):
                self.assertIn('<table class="stack">', self.client.get(url).content.decode())
        self.assertIn("table.stack td[data-label]::before", CSS)
        self.assertIn("content: attr(data-label);", CSS)

    def test_buttons_and_fields_are_at_least_44px_tall(self):
        for selector in (".button {", ".link-button {", ".navbar a {", 'input[type="date"], input[type="number"]'):
            with self.subTest(selector=selector):
                rule = CSS[CSS.index(selector):]
                rule = rule[:rule.index("}")]
                self.assertIn("min-height: 44px;", rule)

    def test_small_screen_rules_exist(self):
        small = CSS[CSS.index("@media (max-width: 640px)"):]
        for rule in (".navbar.collapsible .links { display: none; }", "table.stack thead", ".navbar.collapsible.open .links"):
            with self.subTest(rule=rule):
                self.assertIn(rule, small)
