import json
import logging
from django.views import View
from django.http import JsonResponse
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import get_object_or_404
from functools import wraps

logger = logging.getLogger(__name__)

class ApiView(View):
    """
    Base view for all API endpoints.
    Handles JSON parsing/response and standard error catching.
    """
    
    def dispatch(self, request, *args, **kwargs):
        # SECURITY: Ensure user is authenticated for all API calls
        if not request.user.is_authenticated:
            return self.error_response("Authentication required", status=401)
            
        try:
            return super().dispatch(request, *args, **kwargs)
        except ValidationError as e:
            return self.error_response(getattr(e, 'message', str(e)), status=400)
        except PermissionDenied as e:
            return self.error_response(str(e), status=403)
        except Exception as e:
            logger.exception("Internal Server Error")
            return self.error_response("An unexpected error occurred", status=500)

    def success_response(self, data, status=200):
        return JsonResponse({
            "status": "success",
            "data": data
        }, status=status)

    def error_response(self, message, status=400, errors=None):
        response_data = {
            "status": "error",
            "message": message
        }
        if errors:
            response_data["errors"] = errors
        return JsonResponse(response_data, status=status)

    def get_json_body(self):
        try:
            return json.loads(self.request.body or '{}')
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON body")

def get_business_or_404(request, pk):
    """
    Centralized resolver for Business context with permission check.
    """
    from core.models import Business
    if request.user.is_superuser:
        return get_object_or_404(Business, pk=pk)
    return get_object_or_404(Business, pk=pk, created_by=request.user)

def business_required(view_func):
    """
    Decorator that resolves business context and adds it to the request object.
    Usage: @business_required
           def my_view(request, business, ...):
    """
    @wraps(view_func)
    def _wrapped_view(request, biz_pk, *args, **kwargs):
        business = get_business_or_404(request, biz_pk)
        return view_func(request, business, *args, **kwargs)
    return _wrapped_view
