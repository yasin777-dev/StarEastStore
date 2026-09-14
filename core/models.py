"""Core app models: contact messages and static-page content."""
from django.db import models


class ContactMessage(models.Model):
    """A message submitted through the contact page."""

    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_handled = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'contact message'
        verbose_name_plural = 'contact messages'

    def __str__(self) -> str:
        return f'{self.subject} - {self.name}'
