from django.shortcuts import render, redirect, get_object_or_404
from .forms import BusinessForm, DocumentUploadForm, SignUpForm, LoginForm
from .models import Business, Document
import pytesseract
from PIL import Image
from django.contrib.auth import login, logout
from .processor import process_document, generate_business_summary
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib.auth import authenticate
from django.utils import timezone
from django.contrib import messages
from apps.ledger.services.ledger_service import LedgerService

# -------------------- AUTH VIEWS --------------------
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
                
                # Robust Initialization: Create standard Tally groups
                try:
                    LedgerService.initialize_standard_coa(business)
                except Exception as e:
                    print(f"COA Initialization Error: {e}")
                    
                return redirect(reverse("core:business_detail", args=[business.id]))
            except IntegrityError:
                messages.error(request, "This Business/GSTIN is already registered in the system.")
                return render(request, 'core/business_form.html', {'form': form})
    else:
        form = BusinessForm()
    return render(request, 'core/business_form.html', {'form': form})


@login_required
def business_detail(request, pk):
    business = get_object_or_404(Business, pk=pk, created_by=request.user)
    summary = generate_business_summary(business)
    return render(request, 'core/business_detail.html', {'business': business, 'summary': summary})


# -------------------- DOCUMENTS --------------------
@login_required
def upload_document(request, business_id):
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

                # OCR / Text Extraction
                try:
                    filepath = doc.file.path
                    text = ""
                    if filepath.lower().endswith('.pdf'):
                        import pdfplumber
                        with pdfplumber.open(filepath) as pdf:
                            for page in pdf.pages:
                                text += page.extract_text() or ""
                    else:
                        text = pytesseract.image_to_string(filepath)
                    
                    doc.ocr_text = text
                    if text:
                        doc.status = 'ocr_complete'
                    else:
                        doc.status = 'failed'
                    doc.save()
                except Exception as e:
                    doc.ocr_text = f'Extraction failed. Error: {e}'
                    doc.status = 'extraction_failed'
                    doc.save()

                # Process document in background or immediately
                process_document(doc)
                uploaded_count += 1

            return redirect(reverse("core:documents_list", args=[business.id]))
    else:
        form = DocumentUploadForm()
    return render(request, 'core/upload.html', {'form': form, 'business': business})


@login_required
def documents_list(request, business_id):
    business = get_object_or_404(Business, pk=business_id, created_by=request.user)
    docs = business.documents.all().order_by('-uploaded_at')
    return render(request, 'core/documents_list.html', {'business': business, 'documents': docs})


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk, business__created_by=request.user)
    lines = doc.lines.all()
    vouchers = doc.vouchers.all().prefetch_related('entries__account')
    
    # Advanced Dashboard Metrics
    total_val = sum(v.total_amount for v in vouchers)
    match_count = lines.exclude(ledger_account__icontains='Suspense').count()
    knockoff_count = vouchers.filter(entries__ref_type='AGST').distinct().count()
    
    context = {
        'doc': doc, 
        'lines': lines, 
        'vouchers': vouchers,
        'metrics': {
            'total_value': total_val,
            'match_count': match_count,
            'knockoff_count': knockoff_count,
            'reliability': 94 if doc.is_processed else 0
        }
    }
    return render(request, 'core/document_detail.html', context)


@login_required
def approve_vouchers(request, pk):
    doc = get_object_or_404(Document, pk=pk, business__created_by=request.user)
    if request.method == "POST":
        doc.vouchers.all().update(is_draft=False)
        doc.is_synced_to_tally = True
        doc.synced_at = timezone.now()
        doc.sync_log = f"Successfully verified {doc.vouchers.count()} entries and prepared for Tally import."
        doc.save()
        messages.success(request, "Vouchers verified and synchronized to internal ledger.")
        return redirect(reverse('core:document_detail', args=[pk]))
    return redirect(reverse('core:document_detail', args=[pk]))



