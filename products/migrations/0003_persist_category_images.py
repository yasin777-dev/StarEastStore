"""Store category photos with the catalog instead of on ephemeral web disks."""
import logging

from PIL import Image
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.db import migrations, models

import products.storage

logger = logging.getLogger(__name__)


def preserve_category_images(apps, schema_editor):
    """Copy any surviving legacy files without renaming or deleting originals."""
    alias = schema_editor.connection.alias
    Category = apps.get_model('products', 'Category')
    CatalogImageFile = apps.get_model('products', 'CatalogImageFile')
    blobs = CatalogImageFile.objects.using(alias)
    names = (
        Category.objects.using(alias)
        .exclude(image='').exclude(image__isnull=True)
        .order_by('image').values_list('image', flat=True).distinct()
    )
    legacy_storage = FileSystemStorage()
    unavailable = 0
    for name in names.iterator(chunk_size=100):
        # A database copy is authoritative; don't replace it with a stale disk file.
        if blobs.filter(name=name).exists():
            continue
        try:
            with legacy_storage.open(name, 'rb') as source:
                Image.open(source).verify()
                source.seek(0)
                data = source.read()
        except (OSError, ValueError, SuspiciousFileOperation, Image.DecompressionBombError):
            unavailable += 1
            continue
        blobs.get_or_create(name=name, defaults={'data': data})
    if unavailable:
        logger.warning(
            '%s category image(s) could not be preserved: original files are missing '
            'or invalid. Re-upload those originals in Admin > Products > Categories.',
            unavailable,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('products', '0002_catalogimagefile_alter_productimage_image'),
    ]

    operations = [
        migrations.AlterField(
            model_name='category',
            name='image',
            field=models.ImageField(
                blank=True, null=True, storage=products.storage.CatalogImageStorage(),
                upload_to='categories/',
            ),
        ),
        migrations.RunPython(preserve_category_images, migrations.RunPython.noop),
    ]
