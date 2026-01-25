from django.db import models
from django.conf import settings
from core.models import Business

class EmailTemplate(models.Model):
    """
    Templates for the Agent to use when emailing clients.
    """
    name = models.CharField(max_length=100)
    subject = models.CharField(max_length=200)
    body = models.TextField(help_text="Use {{client_name}}, {{missing_items}} as placeholders")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class CommunicationLog(models.Model):
    """
    Logs all actions taken by the Agentic Workflow.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    message_body = models.TextField()
    
    status = models.CharField(max_length=20, choices=[
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('draft', 'Draft')
    ], default='draft')
    
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    
    # Metadata for the agent logic
    agent_action = models.CharField(max_length=100, default='document_chaser')
    
    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.agent_action} to {self.recipient} on {self.sent_at}"
