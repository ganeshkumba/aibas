# AI‑Based Accounting System (God-Mode Enterprise Edition)

An AI‑powered, CA-Grade accounting SaaS designed specifically for Indian businesses. This system goes beyond basic OCR to provide "God-Level" automation, identifying tax traps, automating reconciliation, and ensuring audit-ready financial statements.

## 🚀 Key Features (God-Mode)

### 1. Multimodal Vision Extraction (Gemini 1.5 Flash)
- **Beyond OCR:** Uses Gemini 1.5 Flash to "see" documents. It recognizes logos, handwritten dates, "PAID" stamps, and semi-legible cursive on small receipts.
- **Contextual Intelligence:** Extracts not just text, but accounting logic (e.g., identifying if a bill is B2B or B2C based on the "Bill-To" section).

### 2. God-Level Indian Accounting Logic
- **MSME 45-Day Trap (Sec 43B(h)):** Automatically detects MSME vendors via Udyam numbers/logos and sets payment deadlines.
- **TDS Applicability (Sec 194I/194J):** Automatically detects RENT or Professional Fees and suggests TDS splits when thresholds are crossed.
- **Fractional GST Round-offs:** Intelligent 1-paisa balancing to ensure Tally XML imports never fail due to tiny rounding differences.
- **B2B vs B2C Detection:** Verified GSTINs in the "Bill To" section. If missing, the system moves tax to the Expense ledger to prevent illegal ITC claims.

### 3. "God-Mode" Reconciliation Engine
- **Ghost Liability Killer:** Automatically matches bank statement withdrawals/deposits to uploaded purchase/sales invoices based on amount and narration keywords.
- **Bill-to-Bill Tracking:** Implements Tally-style `<BILLALLOCATIONS.LIST>` logic to knock off liabilities and ensure vendor balances reach zero.
- **Manual Trigger:** A "God Mode" reconcile button on the Trial Balance to sweep and fix all pending classifications.

### 4. Advanced Financial Health Protocol
- **Real-time Health Checks:** The Trial Balance automatically warns about "Negative Equity," "Zero AssetBase," and "Pending Classifications."
- **One-Click Capital Infusion:** A guided flow to fix "Negative Equity" by recording initial capital investments.

### 5. Multi-Page & Multi-Document Support
- **Bank Statements:** Parses multi-page PDF/Images while tracking running balances.
- **Audit Vault:** A central repository for all processed documents with their AI-generated "Accounting Logic" audit trails.

---

## 🎨 UI/UX: Dark Mode & Premium Aesthetics
- **Dual-Theme Support:** Toggle between "Professional Light" and "Audit Dark" modes.
- **Glassmorphism:** Modern, responsive design with clear visual hierarchies and micro-animations.

---

## 🛠 Tech Stack
- **Backend:** Python 3.13, Django 5.x
- **AI Brain:** Google Gemini 1.5 Flash (Primary), Ollama (Fallback)
- **Database:** SQLite (MVP)
- **Frontend:** Vanilla CSS (Custom Variable-based Theming), JS
- **Compliance:** TallyPrime/ERP 9 XML Standards

---

## 🚦 Quick Start

### 1. Configure Environment
Create a `.env` file:
```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
TESSERACT_CMD=path_to_tesseract
```

### 2. Setup System
```bash
python -m venv venv
venv\Scripts\Activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### 3. The "God-Mode" Flow
1. **Upload:** Head to 'Upload Entry' and drop your messy bank statements or bills.
2. **Review:** Check the 'Audit Vault' for AI-suggested TDS and GST treatments.
3. **Reconcile:** Open 'Trial Balance' and click **Reconcile Ledgers (God Mode)** to clear all pending bank entries.
4. **Export:** Download the Tally XML and import it directly into TallyPrime.

---

## 📄 License
Licensed under Apache 2.0.
