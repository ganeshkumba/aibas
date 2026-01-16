import threading
from django.db.models import Q
from core.models import Business

# Thread-local storage for current multitenancy context
_thread_locals = threading.local()

def get_current_business():
    return getattr(_thread_locals, 'business', None)

class MultitenancyMiddleware:
    """
    Middleware to handle multitenancy context.
    Expects 'X-Business-ID' header or 'business_id' query param.
    Secures data by ensuring the user has access to the requested business.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        business_id = request.headers.get('X-Business-ID') or request.GET.get('business_id')
        
        if business_id and request.user.is_authenticated:
            # Security: Ensure user is the owner or the creator of this business,
            # or is a superuser/staff.
            lookup = Q(id=business_id)
            if not request.user.is_superuser:
                lookup &= (Q(owner=request.user) | Q(created_by=request.user))
            
            business = Business.objects.filter(lookup).first()
            
            if business:
                request.business = business
                _thread_locals.business = business
            else:
                request.business = None
                _thread_locals.business = None
        else:
            request.business = None
            _thread_locals.business = None

        response = self.get_response(request)
        
        # Cleanup to prevent leak to other threads
        if hasattr(_thread_locals, 'business'):
            del _thread_locals.business
            
        return response
