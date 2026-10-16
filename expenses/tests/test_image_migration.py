"""Migrations 0010-0012: receipt image files on disk are copied into the database, then the file field goes."""
import contextlib
import io
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("expenses", "0010_receipt_image_in_database")]
AFTER = [("expenses", "0012_remove_receipt_image_file")]


class CopyImagesMigrationTests(TransactionTestCase):
    serialized_rollback = True  # restore the categories that migration 0002 seeds, for the other tests

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            executor.migrate(targets)
        return executor.loader.project_state(targets).apps, out.getvalue()

    def setUp(self):
        self.media = Path(tempfile.mkdtemp())
        apps, _ = self.migrate(BEFORE)
        User = apps.get_model("expenses", "User")
        Receipt = apps.get_model("expenses", "Receipt")
        user = User.objects.create(username="alice", password="x")
        (self.media / "receipts" / str(user.pk)).mkdir(parents=True)
        (self.media / "receipts" / str(user.pk) / "abc123.JPG").write_bytes(b"\xff\xd8 jpeg on disk")
        self.with_file = Receipt.objects.create(user=user, image=f"receipts/{user.pk}/abc123.JPG").pk
        self.missing_file = Receipt.objects.create(user=user, image=f"receipts/{user.pk}/gone.png").pk
        self.no_image = Receipt.objects.create(user=user, image="").pk

    def tearDown(self):
        shutil.rmtree(self.media, ignore_errors=True)
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_files_are_copied_into_the_database_and_the_file_field_removed(self):
        with mock.patch.dict(os.environ, {"MEDIA_ROOT": str(self.media)}):
            apps, output = self.migrate(AFTER)
        Receipt = apps.get_model("expenses", "Receipt")

        copied = Receipt.objects.get(pk=self.with_file)
        self.assertEqual(bytes(copied.image_data), b"\xff\xd8 jpeg on disk")
        self.assertEqual(copied.image_content_type, "image/jpeg")
        self.assertRegex(copied.image_name, r"^[0-9a-f]{32}\.jpg$")

        for pk in (self.missing_file, self.no_image):
            receipt = Receipt.objects.get(pk=pk)
            self.assertIsNone(receipt.image_data)
            self.assertEqual(receipt.image_name, "")

        self.assertIn("Copied 1 receipt image(s)", output)
        self.assertIn("1 file(s) not found", output)
        self.assertNotIn("image", [f.name for f in Receipt._meta.get_fields()])
        # The files themselves are left for the operator to delete.
        self.assertTrue(any(self.media.rglob("abc123.JPG")))
