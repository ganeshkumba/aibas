import datetime
from django.utils import timezone
from django.db.models import Count, Q
from core.models import Business, ExtractedLineItem
from apps.communication.models import CommunicationLog, EmailTemplate

class DocumentChaserAgent:
    """
    AGENCY LAYER:
    This agent proactively monitors business ledgers and 'Chases' clients 
    for missing documents before the accountant even notices.
    """

    def __init__(self, business: Business):
        self.business = business

    def identify_missing_recurring_vendors(self):
        """
        AI Logic to spot patterns:
        "You usually upload 'AWS' and 'Rent' by the 5th. It's the 10th and they are missing."
        """
        today = datetime.date.today()
        current_month_start = today.replace(day=1)
        six_months_ago = current_month_start - datetime.timedelta(days=180)

        # 1. Find Recurring Vendors (Appeared in at least 2 distinct months in the last 6 months)
        recurring_vendors = (
            ExtractedLineItem.objects.filter(
                document__business=self.business,
                date__gte=six_months_ago,
                date__lt=current_month_start,
                vendor__isnull=False
            )
            .values('vendor')
            .annotate(month_count=Count('date', distinct=True)) # Crude proxy for distinct months
            .filter(month_count__gte=2)
        )
        
        expected_vendors = [v['vendor'] for v in recurring_vendors]
        
        # 2. Check who has NOT been seen specifically in the CURRENT MONTH
        present_this_month = ExtractedLineItem.objects.filter(
            document__business=self.business,
            date__gte=current_month_start,
            vendor__in=expected_vendors
        ).values_list('vendor', flat=True)
        
        missing_vendors = list(set(expected_vendors) - set(present_this_month))
        return missing_vendors

    def draft_chase_email(self):
        """
        Generates the 'Agentic' email content.
        """
        missing_vendors = self.identify_missing_recurring_vendors()
        if not missing_vendors:
            return None # Agent is happy, nothing to do.

        # Get or Create default template
        template, _ = EmailTemplate.objects.get_or_create(
            name="default_chaser",
            defaults={
                "subject": "Action Required: Missing Documents for {{month}}",
                "body": "Hi {{client_name}},\n\nMy AI audit found that we are missing invoices for the following recurring vendors for {{month}}:\n\n{{missing_items}}\n\nPlease upload them to the portal to ensure GST compliance.\n\nRegards,\nThe Ledger AI"
            }
        )
        
        # Fill placeholders
        context = {
            "client_name": self.business.owner.first_name if self.business.owner else "Client",
            "month": datetime.date.today().strftime("%B %Y"),
            "missing_items": "\n".join([f"- {v}" for v in missing_vendors])
        }
        
        body = template.body
        subject = template.subject
        for key, value in context.items():
            body = body.replace(f"{{{{{key}}}}}", str(value))
            subject = subject.replace(f"{{{{{key}}}}}", str(value))

        # Create Log (Draft Mode)
        log = CommunicationLog.objects.create(
            business=self.business,
            recipient=self.business.owner.email if self.business.owner else "unknown@example.com",
            subject=subject,
            message_body=body,
            status='draft',
            agent_action='document_chaser'
        )
        
        return log
