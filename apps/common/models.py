import uuid
from django.db import models
from core.models import Business

class BusinessOwnedModel(models.Model):
    """
    Abstract base class to reduce redundancy across all business-specific models.
    Provides UUID primary key, business relation, and timestamps.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        Business, 
        on_delete=models.CASCADE, 
        related_name="%(class)ss"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
