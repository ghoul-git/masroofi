import importlib
import re
import shutil
import tempfile
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import Resolver404, resolve

from expenses.models import Receipt
from expenses.models.receipt import receipt_image_path
from expenses.tests.factories import make_user

IMAGE_BYTES = b"\xff\xd8\xff\xe0 fake jpeg bytes"
MEDIA_ROOT = tempfile.mkdtemp()


class ReceiptImagePathTests(TestCase):
    def test_path_is_per_user_with_random_name_and_original_extension(self):
        path = receipt_image_path(SimpleNamespace(user_id=42), "My Receipt (Carrefour).JPG")
        self.assertRegex(path, r"^receipts/42/[0-9a-f]{32}\.JPG$")
        self.assertNotIn("Carrefour", path)

    def test_names_are_not_reused(self):
        instance = SimpleNamespace(user_id=1)
        self.assertNotEqual(receipt_image_path(instance, "a.png"), receipt_image_path(instance, "a.png"))

    def test_file_without_extension(self):
        self.assertRegex(receipt_image_path(SimpleNamespace(user_id=1), "photo"), r"^receipts/1/[0-9a-f]{32}$")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ReceiptImageViewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.receipt = Receipt.objects.create(
            user=self.alice,
            image=SimpleUploadedFile("receipt.jpg", IMAGE_BYTES, content_type="image/jpeg"),
        )
        self.url = f"/receipts/{self.receipt.pk}/image/"

    def get(self, url=None):
        # Do not call response.close() here: it sends request_finished, which closes the test
        # database connection. Reading streaming_content to the end closes the file safely.
        return self.client.get(url or self.url)

    def test_saved_under_the_owners_folder_with_a_random_name(self):
        self.assertRegex(self.receipt.image.name, rf"^receipts/{self.alice.pk}/[0-9a-f]{{32}}\.jpg$")

    def test_owner_gets_the_image(self):
        self.client.force_login(self.alice)
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), IMAGE_BYTES)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_logged_out_request_is_sent_to_login_without_the_image(self):
        response = self.get()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    def test_another_users_request_gets_404(self):
        self.client.force_login(self.bob)
        response = self.get()
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(IMAGE_BYTES, response.content)

    def test_unknown_receipt_gets_404(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.get(f"/receipts/{self.receipt.pk + 1000}/image/").status_code, 404)

    def test_missing_file_gets_404(self):
        self.receipt.image.storage.delete(self.receipt.image.name)
        self.client.force_login(self.alice)
        self.assertEqual(self.get().status_code, 404)

    def test_media_url_is_not_served_even_with_debug_on(self):
        # static() only adds its route when DEBUG is on, so rebuild the URLconf with DEBUG=True.
        import config.urls

        with override_settings(DEBUG=True):
            urls = importlib.reload(config.urls)
            with self.assertRaises(Resolver404):
                resolve(f"/media/{self.receipt.image.name}", urlconf=urls)
        importlib.reload(config.urls)
        self.assertFalse(any(re.search("media", str(p.pattern)) for p in config.urls.urlpatterns))
