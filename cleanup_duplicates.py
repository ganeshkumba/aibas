from core.models import Business
try:
    deleted = Business.objects.filter(id=7).delete()
    print(f"Deleted: {deleted}")
except Exception as e:
    print(f"Error: {e}")
