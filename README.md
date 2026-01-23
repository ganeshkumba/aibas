# 🇮🇳 The Ledger: "God-Mode" AI Accounting & Audit Co-Pilot

[![Standard: Indian GAAP](https://img.shields.io/badge/Standard-Indian%20GAAP-blue.svg)](https://en.wikipedia.org/wiki/Generally_Accepted_Accounting_Principles_(India))
[![AI: Gemini 1.5 Flash](https://img.shields.io/badge/AI-Gemini%201.5%20Flash-orange.svg)](https://deepmind.google/technologies/gemini/)
[![Framework: Django 5.x](https://img.shields.io/badge/Framework-Django%205.x-green.svg)](https://www.djangoproject.com/)

---

## 📖 Project Overview: From Clueless to God-Mode
This repository captures the transformation of an "Incomplete & Clueless Accounting System" into a **Professional-Grade Virtual Auditor**. Designed specifically for the Indian statutory landscape, it automates the most painful aspects of bookkeeping—AI extraction, tax compliance, and bank reconciliation.

---

## ✨ God-Mode Feature Set

### 1. 👁️ Multimodal Vision Extraction
Unlike standard OCR, "The Ledger" uses **Gemini 1.5 Flash** as a Vision model.
- **Visual Intelligence:** Reads "PAID" stamps, identifies MSME logos, and deciphers semi-legible handwriting on small, stained thermal receipts.
- **Bill-To Verification:** AI checks if your company's GSTIN is present in the "Bill To" section. If not, it automatically flags the bill as B2C and treats GST as an expense (Preventing illegal ITC claims).
- **Audit Trails:** Every document processing event generates an `accounting_logic` field, explaining why specific TDS or GST treatments were chosen.

### 2. ⚖️ CA-Grade Statutory Compliance
The engine enforces complex Indian accounting rules at the moment of ingestion:
- **MSME 45-Day Trap (Sec 43B(h)):** Detects MSME-registered vendors via Udyam numbers and sets an automated 45-day payment deadline alerts.
- **TDS Splitting (Sec 194I/194J):** Detects "Rent" or "Professional Fees" and automatically splits the credit into `Vendor Payable` and `TDS Payable` if thresholds are met.
- **Fractional GST Rounding:** Implements 1-paisa balancing between CGST and SGST to ensure zero failures during Tally XML imports.
- **Place of Supply (POS):** Automated state-code verification against Business GSTIN to determine CGST/SGST vs IGST.

### 3. 💸 The Reconciliation Engine (Liability Solver)
Solves the "Ghost Liability" problem where bank payments don't match bills.
- **Auto-Matching:** Pauses on "Pending Classification" for bank entries and attempts to pair them with Purchase Invoices using Amount + Narration Fuzzy Keywords (e.g., "NEFT-AMAZON" → "Amazon Web Services").
- **Bill-to-Bill Tracking:** Generates Tally-compliant `<BILLALLOCATIONS.LIST>` tags to "knock off" liabilities automatically.
- **Capital Infusion Flow:** A specialized UI to record initial capital investments or opening balances, instantly resolving "Negative Equity" warnings.

### 4. 📦 AI-Augmented Inventory
Surpassing standard billing apps with "Zero-Setup" inventory.
- **Auto-Ingest:** Automatically populates stock levels when a purchase invoice is uploaded.
- **Batch & Expiry Auditor:** AI automatically extracts "Batch Numbers" and "Expiry Dates" from bills.

### 5. 🛡️ Forensic Shield & Security (New - God Mode)
Moving beyond records into active fraud prevention.
- **Cryptographic Audit Trail:** Audit logs are SHA-256 hashed and chained to prevent tampering. Any break in the chain is instantly flagged.
- **IP Forensic Mapping:** Tracks the physical origin of document uploads. Flags anomalous IPs or suspicious metadata (e.g., "back-dated" PDF origins).
- **Security Hardening:** Implements strict CSP, HSTS, and X-Frame-Options to protect sensitive financial data.

### 6. 📅 Amortization Engine (New - God Mode)
Automates the most complex part of accrual accounting.
- **Auto-Accrual:** Detects prepaid expenses (Rent, Insurance) and automatically schedules monthly recognition journal entries.
- **Tracker:** Visual progress tracking for all active assets and deferred liabilities.

### 7. 🏢 Intercompany Control Tower (New - God Mode)
Designed for group organizations with multiple branches.
- **God-View:** Parent entities can monitor transactions across all subsidiaries in a single view.
- **Symmetry Audit:** Automatically flags intercompany transactions that aren't synced between entities.

### 8. 🎨 Audit-Grade UX/UI
- **Audit Dark Mode:** A high-contrast dark theme designed for professional auditing.
- **Interactive Trial Balance:** Includes a "Virtual CFO" that runs 6+ health checks (Forensic Warnings, Negative Equity, etc.).
- **Performance Report:** Real-time visibility into database latency and integrity status.

---

## 🏗️ Technical Architecture

### **Apps & Modules**
- **`core/`**: The backbone. Manages Business entities, Documents, and the high-speed `Processor` (AI Ingestion).
- **`apps/ledger/`**: The Double-Entry Engine. Enforces GAAP rules, manages the Chart of Accounts, and generates Financial Statements (Trial Balance, P&L, Balance Sheet).
- **`apps/audit/`**: **(New)** The Trust Layer. Implements SHA-256 hash-chained logs for immutable financial event tracking.
- **`apps/ai_bridge/`**: The AI Gateway. Supports **Gemini 1.5 Flash** (Vision) and **Ollama** (Local Fallback).
- **`apps/accounts/`**: Custom user management and authentication (Email-based login).

### **Core Services**
- **`AutomationService`**: Bridges documents to vouchers. Handles statutory splits (TDS/GST) and the Reconciliation Engine.
- **`LedgerService`**: The "CFO" logic. Generates health checks, manages voucher numbering, and handles multi-ledger balancing.
- **`ForensicService`**: **(New)** Analyzes document metadata and IP anomalies to detect fraud early.
- **`AmortizationEngine`**: **(New)** Manages deferred expenses and automated monthly recognition.
- **`DocumentProcessor`**: Orchestrates AI extraction and database persistence.

---

## 🚦 Installation & Setup

### 1. Requirements
- Python 3.13+
- Tesseract OCR (Optional Fallback)
- **Google AI Studio Key** (Required for God-Mode Vision)

### 2. Environment Configuration
Create a `.env` file in the root:
```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
DB_NAME=db.sqlite3
DEBUG=True
```

### 3. Quick Run
```bash
# Install dependencies
pip install -r requirements.txt

# Database Setup
python manage.py migrate
python manage.py createsuperuser

# Start Server
python manage.py runserver
```

---

## 📜 Productivity & Logic Log
The project maintains a detailed **Daily Productivity Log** located at `project_analysis/daily_productivity_log.md`, tracking every major issue resolved from "Logic Failures" to "Vision Integrations."

---

## 🗺️ Future Roadmap
- [ ] **Multi-Currency Support:** For Indian businesses with foreign export invoices.
- [ ] **Handwritten Regional Logic:** Supporting receipts in Devanagari (Hindi) and South Indian scripts.
- [ ] **Auto-Generated GSTR-2B Recon:** Matching AI documents against government portal data.

## 📄 License
Licensed under Apache 2.0. Developed by the **Advanced Agentic Coding** team to transform fragmented codebases into elite financial tools.

---
**"Don't just record transactions. Audit the future."**
