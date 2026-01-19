import threading
from django.conf import settings
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from .forms import BusinessForm, DocumentUploadForm, SignUpForm, LoginForm
from .models import Business, Document
import pytesseract
from PIL import Image
from django.contrib.auth import login, logout
from .processor import process_document
from django.contrib.auth.decorators import login_required, login_not_required
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.contrib.auth import authenticate
from django.utils import timezone
from django.contrib import messages
from apps.ledger.services.ledger_service import LedgerService
from apps.ledger.services.cfo_service import CFOService

# -------------------- AUTH VIEWS --------------------
@login_not_required
def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(reverse("core:index"))
    else:
        form = SignUpForm()
    return render(request, "core/signup.html", {"form": form})


@login_not_required
def login_view(request):
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect(reverse("core:index"))
    else:
        form = LoginForm()
    return render(request, "core/login.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    return redirect(reverse("core:login"))


# -------------------- DASHBOARD / BUSINESS --------------------
@login_required
def index(request):
    businesses = Business.objects.filter(created_by=request.user).order_by('-created_at')
    return render(request, 'core/index.html', {'businesses': businesses})


@login_required
def business_create(request):
    if request.method == 'POST':
        form = BusinessForm(request.POST)
        if form.is_valid():
            try:
                from django.db import IntegrityError
                business = form.save(commit=False)
                business.created_by = request.user
                business.save()
                
                # Robust Initialization: Create standard Tally groups & current Financial Year
                try:
                    LedgerService.initialize_standard_coa(business)
                    LedgerService.initialize_financial_year(business)
                except Exception as e:
                    print(f"Business Initialization Error: {e}")
                    
                return redirect(reverse("core:business_detail", args=[business.id]))
            except IntegrityError:
                messages.error(request, "This Business/GSTIN is already registered in the system.")
                return render(request, 'core/business_form.html', {'form': form})
    else:
        form = BusinessForm()
    return render(request, 'core/business_form.html', {'form': form})


@login_required
def business_detail(request, pk):
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=pk)
    else:
        business = get_object_or_404(Business, pk=pk, created_by=request.user)
    summary = CFOService.get_executive_summary(business)
    return render(request, 'core/business_detail.html', {'business': business, 'summary': summary})


# -------------------- DOCUMENTS --------------------
@login_required
def upload_document(request, business_id):
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=business_id)
    else:
        business = get_object_or_404(Business, pk=business_id, created_by=request.user)
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            doc_type = form.cleaned_data['doc_type']
            files = request.FILES.getlist('file')
            
            uploaded_count = 0
            for uploaded_file in files:
                doc = Document(
                    business=business,
                    uploaded_by=request.user,
                    file=uploaded_file,
                    doc_type=doc_type
                )
                doc.save()

                # Start AI in a background thread
                thread = threading.Thread(target=process_document, args=(doc.id,))
                thread.daemon = True
                thread.start()
                uploaded_count += 1

            return redirect(reverse("core:documents_list", args=[business.id]))
    else:
        form = DocumentUploadForm()
    return render(request, 'core/upload.html', {'form': form, 'business': business})


@login_required
def documents_list(request, business_id):
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=business_id)
    else:
        business = get_object_or_404(Business, pk=business_id, created_by=request.user)
    docs = business.documents.all().order_by('-uploaded_at')
    return render(request, 'core/documents_list.html', {'business': business, 'documents': docs})


@login_required
def document_detail(request, pk):
    if request.user.is_superuser:
        doc = get_object_or_404(Document, pk=pk)
    else:
        doc = get_object_or_404(Document, pk=pk, business__created_by=request.user)
    lines = doc.lines.all()
    vouchers = doc.vouchers.all().prefetch_related('entries__account')
    
    # Financial Analytics (Business-wide)
    cfo_summary = CFOService.get_executive_summary(doc.business)
    
    # Document-specific metrics
    doc_total = sum((v.total_amount for v in vouchers), Decimal('0.00'))
    processed_count = lines.exclude(ledger_account__icontains='Pending').count()
    
    context = {
        'doc': doc, 
        'business': doc.business,
        'lines': lines, 
        'vouchers': vouchers,
        'all_accounts': doc.business.accounts.all().select_related('group').order_by('name'),
        'all_groups': doc.business.account_groups.all().order_by('name'),
        'metrics': {
            'total_value': doc_total,
            'match_count': processed_count,
            'reliability': doc.confidence if doc.is_processed else 0,
            'burn_rate': cfo_summary['burn_rate'],
            'tax_savings': cfo_summary['tax_savings'],
            'business_pl': cfo_summary['net_profit_loss']
        },
        'health': cfo_summary['health_checks'],
        'ollama_model': getattr(settings, 'OLLAMA_MODEL', 'llama3.1')
    }
    return render(request, 'core/document_detail.html', context)


@login_required
@require_POST
def approve_vouchers(request, pk):
    print(f"DEBUG: Entering approve_vouchers for PK {pk}")
    if request.user.is_superuser:
        doc = get_object_or_404(Document, pk=pk)
    else:
        doc = get_object_or_404(Document, pk=pk, business__created_by=request.user)
    doc.vouchers.all().update(is_draft=False)
    doc.is_synced_to_tally = True
    doc.synced_at = timezone.now()
    doc.sync_log = f"Successfully verified {doc.vouchers.count()} entries and prepared for Tally import."
    doc.save()
    messages.success(request, "Vouchers verified and synchronized to internal ledger.")
    return redirect(reverse('core:document_detail', args=[pk]))


@login_required
@require_POST
def reprocess_document(request, pk):
    print(f"DEBUG: Entering reprocess_document for PK {pk}")
    if request.user.is_superuser:
        doc = get_object_or_404(Document, pk=pk)
    else:
        doc = get_object_or_404(Document, pk=pk, business__created_by=request.user)
    
    # 1. Reset document state immediately
    doc.lines.all().delete()
    doc.vouchers.all().delete()
    doc.status = 'processing'
    doc.is_processed = False
    doc.extraction_errors = {}
    doc.save()
    
    # 2. Start AI in a background thread
    from core.processor import process_document
    thread = threading.Thread(target=process_document, args=(doc.id,))
    thread.daemon = True # Thread dies if main process dies
    thread.start()
    
    messages.info(request, "AI analysis started in background. Please refresh in a few moments.")
    return redirect(reverse('core:document_detail', args=[pk]))


@login_required
@require_POST
def update_ocr_text(request, pk):
    """
    Expert Mode: Allows CAs to correct OCR mistakes manually before AI extraction.
    """
    if request.user.is_superuser:
        doc = get_object_or_404(Document, pk=pk)
    else:
        doc = get_object_or_404(Document, pk=pk, business__created_by=request.user)
    
    new_text = request.POST.get('ocr_text', '')
    doc.ocr_text = new_text
    doc.save()
    
    if 'process_ai' in request.POST:
        # Reset state for full AI reprocessing
        doc.lines.all().delete()
        doc.vouchers.all().delete()
        doc.status = 'processing'
        doc.is_processed = False
        doc.extraction_errors = {}
        doc.save()
        
        from core.processor import process_document
        thread = threading.Thread(target=process_document, args=(doc.id,))
        thread.daemon = True
        thread.start()
        messages.success(request, "OCR text corrected. AI Re-extraction started in background.")
    else:
        messages.success(request, "OCR text updated. Document is now ready for manual or AI processing.")
        
    return redirect(reverse('core:document_detail', args=[pk]))



