import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.ledger.services.ledger_service import LedgerService
from .forms import BusinessForm
from .models import Business


def health(request):
    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["GET"])
def current_user(request):
    return JsonResponse(
        {
            "id": request.user.id,
            "email": request.user.email,
            "full_name": getattr(request.user, "full_name", ""),
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def businesses(request):
    if request.method == "GET":
        qs = Business.objects.filter(created_by=request.user).prefetch_related("documents")
        payload = [
            {
                "id": b.id,
                "name": b.name,
                "pan": b.pan,
                "gstin": b.gstin,
                "state": b.state,
                "documents_count": b.documents.count(),
                "detail_url": f"/businesses/{b.id}/",
            }
            for b in qs
        ]
        return JsonResponse({"businesses": payload})

    body = json.loads(request.body or "{}")
    form = BusinessForm(body)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    business = form.save(commit=False)
    business.created_by = request.user
    business.save()
    try:
        LedgerService.initialize_standard_coa(business)
        LedgerService.initialize_financial_year(business)
    except Exception:
        # Do not block UI creation if optional initialization fails.
        pass

    return JsonResponse(
        {
            "id": business.id,
            "name": business.name,
            "pan": business.pan,
            "gstin": business.gstin,
            "state": business.state,
            "documents_count": 0,
            "detail_url": f"/businesses/{business.id}/",
        },
        status=201,
    )
