"""Copy receipt images saved as files on disk into Receipt.image_data.

Runs before 0012 removes the old image field. Images are read from MEDIA_ROOT if
that environment variable is set, otherwise from media/ in the project, which is
where they were saved before. A missing file is reported and skipped: that
receipt keeps no image, as if it had already been confirmed. The files are not
deleted; remove the media folder once the migration has run.
"""
import mimetypes
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.db import migrations


def media_root() -> Path:
    return Path(os.getenv("MEDIA_ROOT", "").strip() or Path(settings.BASE_DIR) / "media")


def copy_images(apps, schema_editor):
    Receipt = apps.get_model("expenses", "Receipt")
    root = media_root()
    copied = missing = 0
    for receipt in Receipt.objects.exclude(image="").filter(image_data__isnull=True).only("id", "image").iterator():
        path = root / receipt.image.name
        try:
            data = path.read_bytes()
        except OSError:
            missing += 1
            continue
        extension = Path(receipt.image.name).suffix.lower()
        Receipt.objects.filter(pk=receipt.pk).update(
            image_data=data,
            image_content_type=mimetypes.guess_type(f"x{extension}")[0] or "application/octet-stream",
            image_name=f"{uuid.uuid4().hex}{extension}"[:100],
        )
        copied += 1
    if copied or missing:
        print(f"\n  Copied {copied} receipt image(s) from {root} into the database; {missing} file(s) not found.")


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0010_receipt_image_in_database"),
    ]

    operations = [
        # Going back leaves image_data as it is: the old image field is restored empty by 0012's reverse.
        migrations.RunPython(copy_images, migrations.RunPython.noop),
    ]
