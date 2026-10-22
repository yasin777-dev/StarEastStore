"""Category uploads must survive loss of the web server's local media folder."""
import io
import tempfile
from importlib import import_module
from types import SimpleNamespace
from pathlib import Path

from PIL import Image
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import connection
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import CatalogImageFile, Category


def image_bytes(color='blue', image_format='PNG'):
    output = io.BytesIO()
    Image.new('RGB', (16, 16), color).save(output, format=image_format)
    return output.getvalue()


class CategoryImageUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('category-admin@example.com')

    def setUp(self):
        self.media_root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=self.media_root))
        self.client.force_login(self.admin)

    def upload_category(self):
        data = image_bytes()
        response = self.client.post(reverse('admin:products_category_add'), {
            'name': 'Electronics', 'slug': 'electronics', 'is_active': 'on',
            'image': SimpleUploadedFile('category.png', data, content_type='image/png'),
        })
        self.assertEqual(response.status_code, 302)
        return Category.objects.get(slug='electronics'), data

    def assert_public_image(self, url, data):
        response = Client().get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(b''.join(response.streaming_content), data)
        response.close()

    def test_admin_upload_is_saved_in_database_not_on_local_disk(self):
        category, data = self.upload_category()
        blob = CatalogImageFile.objects.get(name=category.image.name)
        self.assertEqual(bytes(blob.data), data)
        self.assertFalse(any(Path(self.media_root).rglob('*')))
        self.assertTrue(category.image.url.startswith('/catalog-images/'))

    def test_category_photo_survives_empty_media_folder_in_production(self):
        category, data = self.upload_category()
        with tempfile.TemporaryDirectory() as other_server, override_settings(
            MEDIA_ROOT=other_server, DEBUG=False, SERVE_MEDIA=False,
        ):
            category.refresh_from_db()
            self.assert_public_image(category.image.url, data)
            home = Client().get(reverse('core:home'))
            self.assertContains(home, f'src="{category.image.url}"')
            self.assertNotContains(home, 'src="/media/categories/')

    def test_replacing_same_filename_uses_fresh_url_and_preserves_new_bytes(self):
        category, original = self.upload_category()
        old_url = category.image.url
        replacement = image_bytes('red')
        response = self.client.post(reverse('admin:products_category_change', args=[category.pk]), {
            'name': category.name, 'slug': category.slug, 'is_active': 'on',
            'image': SimpleUploadedFile('category.png', replacement, content_type='image/png'),
        })
        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertNotEqual(category.image.url, old_url)
        with tempfile.TemporaryDirectory() as empty, override_settings(MEDIA_ROOT=empty):
            self.assert_public_image(category.image.url, replacement)
            self.assert_public_image(old_url, original)
        self.assertEqual(CatalogImageFile.objects.count(), 2)

    def test_editing_category_without_upload_keeps_persisted_photo(self):
        category, data = self.upload_category()
        old_url = category.image.url
        response = self.client.post(reverse('admin:products_category_change', args=[category.pk]), {
            'name': 'Updated electronics', 'slug': category.slug, 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertEqual(category.image.url, old_url)
        self.assertEqual(CatalogImageFile.objects.count(), 1)
        self.assert_public_image(category.image.url, data)

    def test_clearing_category_image_uses_existing_icon_fallback(self):
        category, _ = self.upload_category()
        old_url = category.image.url
        response = self.client.post(reverse('admin:products_category_change', args=[category.pk]), {
            'name': category.name, 'slug': category.slug, 'is_active': 'on', 'image-clear': 'on',
        })
        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertFalse(category.image)
        home = Client().get(reverse('core:home'))
        self.assertNotContains(home, old_url)
        self.assertContains(home, 'se-category-icon')

    def test_invalid_image_is_rejected_without_saving_a_blob(self):
        response = self.client.post(reverse('admin:products_category_add'), {
            'name': 'Invalid image', 'slug': 'invalid-image', 'is_active': 'on',
            'image': SimpleUploadedFile('broken.png', b'not an image', content_type='image/png'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload a valid image.')
        self.assertFalse(Category.objects.exists())
        self.assertFalse(CatalogImageFile.objects.exists())


class LegacyCategoryImageMigrationTests(TestCase):
    def setUp(self):
        self.media_root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=self.media_root))
        self.legacy_storage = FileSystemStorage()
        self.migration = import_module('products.migrations.0003_persist_category_images')

    def preserve(self):
        self.migration.preserve_category_images(apps, SimpleNamespace(connection=connection))

    def test_readable_legacy_photo_is_preserved_without_renaming_or_deleting(self):
        data = image_bytes()
        name = self.legacy_storage.save('categories/legacy.png', ContentFile(data))
        category = Category.objects.create(name='Legacy category', image=name)
        updated_at = category.updated_at
        self.preserve()
        category.refresh_from_db()
        self.assertEqual(category.image.name, name)
        self.assertEqual(category.updated_at, updated_at)
        self.assertEqual(bytes(CatalogImageFile.objects.get(name=name).data), data)
        self.assertTrue(self.legacy_storage.exists(name))
        with tempfile.TemporaryDirectory() as empty, override_settings(
            MEDIA_ROOT=empty, DEBUG=False, SERVE_MEDIA=False,
        ):
            response = self.client.get(category.image.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'image/png')
            self.assertEqual(b''.join(response.streaming_content), data)
            response.close()

    def test_backfill_is_repeatable_and_shared_filenames_are_not_duplicated(self):
        name = self.legacy_storage.save('categories/shared.png', ContentFile(image_bytes()))
        Category.objects.create(name='First category', image=name)
        Category.objects.create(name='Second category', image=name)
        self.preserve()
        self.preserve()
        self.assertEqual(CatalogImageFile.objects.count(), 1)
        self.assertEqual(Category.objects.filter(image=name).count(), 2)

    def test_existing_database_copy_is_not_overwritten_by_stale_disk_file(self):
        original = image_bytes('blue')
        name = self.legacy_storage.save('categories/existing.png', ContentFile(image_bytes('red')))
        Category.objects.create(name='Already preserved', image=name)
        CatalogImageFile.objects.create(name=name, data=original)
        self.preserve()
        self.assertEqual(CatalogImageFile.objects.count(), 1)
        self.assertEqual(bytes(CatalogImageFile.objects.get(name=name).data), original)

    def test_missing_and_invalid_files_are_reported_without_erasing_references(self):
        missing = Category.objects.create(name='Missing photo', image='categories/missing.png')
        invalid_name = self.legacy_storage.save('categories/invalid.png', ContentFile(b'not an image'))
        invalid = Category.objects.create(name='Invalid photo', image=invalid_name)
        Category.objects.create(name='No photo', image='')
        Category.objects.create(name='Null photo', image=None)
        with self.assertLogs(self.migration.__name__, level='WARNING') as logs:
            self.preserve()
        self.assertIn('2 category image(s) could not be preserved', logs.output[0])
        self.assertFalse(CatalogImageFile.objects.exists())
        missing.refresh_from_db()
        invalid.refresh_from_db()
        self.assertEqual(missing.image.name, 'categories/missing.png')
        self.assertEqual(invalid.image.name, invalid_name)

    def test_backfill_cannot_read_outside_media_root(self):
        with tempfile.TemporaryDirectory() as parent:
            Path(parent, 'private.png').write_bytes(image_bytes())
            with override_settings(MEDIA_ROOT=Path(parent, 'media')):
                Category.objects.create(name='Invalid path', image='../private.png')
                with self.assertLogs(self.migration.__name__, level='WARNING'):
                    self.preserve()
        self.assertFalse(CatalogImageFile.objects.exists())
