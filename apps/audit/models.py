from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
import uuid
import hashlib
import json

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50, db_index=True) # CREATE, UPDATE, DELETE, APPROVE
    
    # Generic relationship to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    changes = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    reason = models.TextField(blank=True, null=True)
    
    # Forensic / Integrity Fields (GOD-MODE SECURITY)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    previous_hash = models.CharField(max_length=64, blank=True, null=True, help_text="Hash of the preceding audit entry")
    entry_hash = models.CharField(max_length=64, blank=True, null=True, help_text="HMAC/Hash of this specific entry")

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['timestamp']),
        ]

    def generate_hash(self):
        """
        Creates a SHA-256 fingerprint of the log entry.
        """
        payload = {
            "user": str(self.user_id),
            "action": self.action,
            "object_id": str(self.object_id),
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "prev": self.previous_hash or ""
        }
        encoded = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()

    def save(self, *args, **kwargs):
        if not self.previous_hash:
            last_entry = AuditLog.objects.order_by('-timestamp').first()
            if last_entry and last_entry.id != self.id:
                self.previous_hash = last_entry.entry_hash
        
        if not self.timestamp:
             from django.utils import timezone
             self.timestamp = timezone.now()
             
        self.entry_hash = self.generate_hash()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} {self.action} {self.content_type} at {self.timestamp}"
