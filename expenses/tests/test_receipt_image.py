"""Receipt images are stored in the database and served to their owner only."""
import io
import re

from django.contrib.admin.sites import site as admin_site
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import Resolver404, resolve
from PIL import Image

from expenses.models import Receipt
from expenses.models.receipt import random_image_name
from expenses.tests.factories import IMAGE_BYTES, make_receipt, make_user


def png_upload(name="My Receipt (Carrefour).PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/x-not-trusted"), buffer.getvalue()


class RandomImageNameTests(SimpleTestCase):
    def test_random_name_keeps_only_the_extension(self):
        name = random_image_name("My Receipt (Carrefour).JPG")
        self.assertRegex(name, r"^[0-9a-f]{32}\.jpg$")
        self.assertNotIn("Carrefour", name)

    def test_names_are_not_reused(self):
        self.assertNotEqual(random_image_name("a.png"), random_image_name("a.png"))

    def test_file_without_extension_and_length_limit(self):
        self.assertRegex(random_image_name("photo"), r"^[0-9a-f]{32}$")
        self.assertLessEqual(len(random_image_name("x." + "a" * 200)), 100)


class UploadStoresTheImageTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_upload_stores_the_bytes_type_and_a_random_name_in_the_database(self):
        upload, data = png_upload()
        response = self.client.post("/api/receipts/", {"image": upload})
        self.assertEqual(response.status_code, 202)
        receipt = Receipt.objects.get()
        self.assertEqual(bytes(receipt.image_data), data)
        self.assertEqual(receipt.image_content_type, "image/png")  # from Pillow, not the browser
        self.assertRegex(receipt.image_name, r"^[0-9a-f]{32}\.png$")
        self.assertNotIn("image_data", response.json())
        self.assertNotIn("image", response.json())

    def test_image_over_10_mb_is_rejected(self):
        big = SimpleUploadedFile("big.jpg", b"\xff" * (10 * 1024 * 1024 + 1), content_type="image/jpeg")
        response = self.client.post("/api/receipts/", {"image": big})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Receipt.objects.exists())

    def test_status_api_never_returns_the_image(self):
        receipt = make_receipt(self.user)
        body = self.client.get(f"/api/receipts/{receipt.pk}/").content
        self.assertNotIn(b"image_data", body)
        self.assertNotIn(b"fake jpeg bytes", body)

    def test_the_model_has_no_file_field_left(self):
        self.assertEqual([f.name for f in Receipt._meta.get_fields() if f.name.startswith("image")],
                         ["image_data", "image_content_type", "image_name"])


class ReceiptImageViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.receipt = make_receipt(self.alice)
        self.url = f"/receipts/{self.receipt.pk}/image/"

    def test_owner_gets_the_image_with_its_content_type(self):
        self.client.force_login(self.alice)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, IMAGE_BYTES)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_logged_out_request_is_sent_to_login_without_the_image(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    def test_another_users_request_gets_404(self):
        self.client.force_login(self.bob)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(IMAGE_BYTES, response.content)

    def test_unknown_receipt_gets_404(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(f"/receipts/{self.receipt.pk + 1000}/image/").status_code, 404)

    def test_receipt_without_an_image_gets_404(self):
        self.client.force_login(self.alice)
        receipt = make_receipt(self.alice, status=Receipt.Status.CONFIRMED, image_data=None)
        self.assertEqual(self.client.get(f"/receipts/{receipt.pk}/image/").status_code, 404)

    def test_there_is_no_media_url(self):
        import config.urls

        with self.assertRaises(Resolver404):
            resolve("/media/receipts/1/x.jpg")
        self.assertFalse(any(re.search("media", str(p.pattern)) for p in config.urls.urlpatterns))


class ReceiptAdminTests(TestCase):
    def setUp(self):
        admin = make_user("admin")
        admin.is_staff = admin.is_superuser = True
        admin.save()
        self.client.force_login(admin)
        self.receipt = make_receipt(make_user("alice"))

    def test_list_view_does_not_load_or_show_the_image(self):
        model_admin = admin_site._registry[Receipt]
        self.assertNotIn("image_data", model_admin.list_display)
        receipt = model_admin.get_queryset(None).get(pk=self.receipt.pk)
        self.assertIn("image_data", receipt.get_deferred_fields())
        response = self.client.get("/admin/expenses/receipt/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"fake jpeg bytes", response.content)

    def test_detail_page_shows_only_the_size(self):
        response = self.client.get(f"/admin/expenses/receipt/{self.receipt.pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{len(IMAGE_BYTES) / 1024:.1f} KB")
        self.assertNotIn(b"fake jpeg bytes", response.content)
        self.assertNotIn(b'name="image_data"', response.content)

    def test_detail_page_without_an_image(self):
        receipt = make_receipt(make_user("bob"), image_data=None)
        self.assertContains(self.client.get(f"/admin/expenses/receipt/{receipt.pk}/change/"), "No image stored")
