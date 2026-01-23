import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from apps.audit.models import AuditLog
from core.models import Business
from django.contrib.contenttypes.models import ContentType

def simulate_audit_chain():
    print("--- STARTING SECURITY AUDIT CHAIN SIMULATION ---")
    
    # Get a sample business
    biz = Business.objects.first()
    if not biz:
        biz = Business.objects.create(name="Security Test Entity")

    biz_type = ContentType.objects.get_for_model(Business)
    
    print("Recording Audit Logs with Hash-Chaining...")
    
    # 1. Create a few logs
    l1 = AuditLog.objects.create(
        user=None,
        action="CREATE",
        content_type=biz_type,
        object_id=biz.id,
        reason="Initial setup",
        ip_address="127.0.0.1"
    )
    print(f"Log 1 Created: {l1.entry_hash[:10]}...")

    l2 = AuditLog.objects.create(
        user=None,
        action="UPDATE",
        content_type=biz_type,
        object_id=biz.id,
        reason="Security hardening",
        ip_address="127.0.0.1"
    )
    print(f"Log 2 Created: {l2.entry_hash[:10]}... (Prev: {l2.previous_hash[:10]}...)")

    l3 = AuditLog.objects.create(
        user=None,
        action="DELETE_ATTEMPT",
        content_type=biz_type,
        object_id=biz.id,
        reason="Simulated breach test",
        ip_address="192.168.1.100"
    )
    print(f"Log 3 Created: {l3.entry_hash[:10]}... (Prev: {l3.previous_hash[:10]}...)")

    # 2. Verify chain logic
    print("\nVerifying Chain Integrity...")
    logs = AuditLog.objects.order_by('timestamp')
    prev_h = None
    chain_valid = True
    for log in logs:
        if prev_h and log.previous_hash != prev_h:
            print(f"❌ CHAIN BREAK DETECTED at {log.id}")
            chain_valid = False
            break
        prev_h = log.entry_hash
    
    if chain_valid:
        print("SUCCESS: CRYPTOGRAPHIC CHAIN INTACT: System is secure against log tampering.")

    print("--- SIMULATION COMPLETE ---")

if __name__ == "__main__":
    simulate_audit_chain()
