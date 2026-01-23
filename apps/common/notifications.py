import logging
import datetime
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Elite Notification Engine.
    Handles Quota alerts, Compliance reminders, and WhatsApp Simulation.
    """

    @staticmethod
    def send_quota_alert(provider_name, fallback_name):
        """
        Notify the admin that the primary AI provider is exhausted.
        """
        log_msg = f"GOD-MODE ALERT: {provider_name} Quota Exceeded. Fallback to {fallback_name} active."
        logger.warning(log_msg)
        
        # In a real app, this would send an Email/SMS.
        # For this simulator, we just log it as a critical system event.
        print(f"\n[CRITICAL] {log_msg}\n")

    @staticmethod
    def simulate_whatsapp(business, message_type, data):
        """
        GOD-MODE: WhatsApp Notification Simulator.
        Generates a simulated 'WhatsApp' visual for the UI.
        """
        templates = {
            'MSME_DEADLINE': "🚨 *COMPLIANCE ALERT*\nDear {owner},\n\nYour bill #{ref} from *{vendor}* has a mandatory MSME payment deadline on *{date}* (Section 43B(h)).\n\nAvoid tax disallowance by paying before {date}.",
            
            'GST_REMINDER': "⚖️ *GST REMINDER*\n{business_name}\n\nYour GSTR-3B filing is due on *{date}*.\nEstimated ITC: ₹{itc}\n\nProcessed by The Ledger.",
            
            'QUOTA_WARN': "⚠️ *SYSTEM NOTICE*\nAI Capacity reached for Gemini. Switching to Local Engine (Ollama). Processing may be slower.",
            
            'PRODUCT_LOW_STOCK': "📦 *STOCK ALERT*\nProduct: *{product}*\nis below threshold! Current Stock: {qty} {uom}.\n\nReorder now to avoid stockout."
        }

        template = templates.get(message_type, "New notification from The Ledger.")
        formatted_message = template.format(**data)
        
        # Log the simulation
        logger.info(f"WhatsApp Simulated for {business.name}: {message_type}")
        
        return {
            'platform': 'WhatsApp',
            'business': business.name,
            'timestamp': timezone.now(),
            'content': formatted_message,
            'status': 'Simulated'
        }

    @classmethod
    def check_and_notify_deadlines(cls, business):
        """
        Scans upcoming deadlines and 'sends' reminders.
        """
        from apps.ledger.services.cfo_service import CFOService
        calendar = CFOService.get_statutory_calendar(business)
        today = datetime.date.today()
        
        notifications = []
        for event in calendar:
            days_left = (event['date'] - today).days
            if 0 <= days_left <= 3: # 3-day window
                msg_data = {
                    'owner': business.created_by.username if business.created_by else 'Partner',
                    'ref': event.get('title', 'Tax Entry'),
                    'vendor': event.get('description', '').split('for ')[-1].replace('.', '') if 'MSME' in event['type'] else '',
                    'date': event['date'].strftime('%d %b'),
                    'business_name': business.name,
                    'itc': 'Check Dashboard'
                }
                
                type_key = 'MSME_DEADLINE' if event['type'] == 'MSME' else 'GST_REMINDER'
                notifications.append(cls.simulate_whatsapp(business, type_key, msg_data))
        
        return notifications
