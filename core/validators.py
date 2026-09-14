"""File-upload validation shared by forms and admin (section 18)."""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from django.conf import settings

ALLOWED_IMAGE_TYPES = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
}
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def validate_image(image):
    """
    Validate an uploaded image: extension, content type, magic bytes and size.

    Raises ``ValidationError`` for anything that is not a JPEG/PNG/WebP image
    under ``settings.MAX_IMAGE_UPLOAD_SIZE`` bytes.
    """
    if not image:
        return
    if hasattr(image, 'name'):
        import os
        ext = os.path.splitext(image.name)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError(
                _('Unsupported file extension "%(ext)s". Allowed: %(allowed)s.'),
                params={'ext': ext, 'allowed': ', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))},
            )
    content_type = getattr(image, 'content_type', None) or getattr(image.file, 'content_type', None)
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(_('File is not a valid image (JPEG, PNG or WebP).'))

    # Magic byte sniffing - do not trust the client-supplied content type.
    image.seek(0)
    header = image.read(12)
    image.seek(0)
    if not (
        header.startswith(b'\xff\xd8\xff')            # JPEG
        or header.startswith(b'\x89PNG\r\n\x1a\n')    # PNG
        or header.startswith(b'RIFF') and header[8:12] == b'WEBP'  # WebP
    ):
        raise ValidationError(_('Uploaded file does not look like a real image.'))

    size = getattr(image, 'size', None)
    max_size = settings.MAX_IMAGE_UPLOAD_SIZE
    if size and size > max_size:
        raise ValidationError(
            _('Image too large (%(size).1f MB). Maximum allowed is %(max).1f MB.'),
            params={'size': size / (1024 * 1024), 'max': max_size / (1024 * 1024)},
        )
