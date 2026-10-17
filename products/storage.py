"""Small catalog uploads persisted alongside the catalog, not on ephemeral disks."""
import uuid
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.urls import reverse
from django.utils.deconstruct import deconstructible


@deconstructible
class CatalogImageStorage(Storage):
    def _open(self, name, mode='rb'):
        from .models import CatalogImageFile
        try:
            blob = CatalogImageFile.objects.get(name=name)
        except CatalogImageFile.DoesNotExist:
            return FileSystemStorage().open(name, mode)
        return ContentFile(bytes(blob.data), name=name)

    def _save(self, name, content):
        from .models import CatalogImageFile
        CatalogImageFile.objects.create(name=name, data=content.read())
        return name

    def get_available_name(self, name, max_length=None):
        # Immutable URLs also avoid stale browser caches after replacing a photo.
        return f'catalog/{uuid.uuid4().hex}{Path(name).suffix.lower()}'

    def exists(self, name):
        from .models import CatalogImageFile
        return CatalogImageFile.objects.filter(name=name).exists() or FileSystemStorage().exists(name)

    def size(self, name):
        with self.open(name) as image:
            return image.size

    def delete(self, name):
        from .models import CatalogImageFile
        CatalogImageFile.objects.filter(name=name).delete()

    def url(self, name):
        return reverse('products:image', kwargs={'name': name})
