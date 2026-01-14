# AI‑Based Accounting System (MVP)

An AI‑powered accounting SaaS MVP that automates core accounting tasks such as ingesting documents, extracting key fields, and preparing basic summaries for accountants and businesses.

The current codebase focuses on:
- A Django project `acctproj` with a `core` app for business and document management.
- OCR‑based extraction using Tesseract.
- Simple rule‑based and AI‑assisted parsing into line items.
- A basic web UI to sign up, log in, register businesses, upload documents, and view extracted data.

---

## Features (Current MVP)

### 1. Document Processing
- Upload invoices, receipts, bills, and bank statements as image files.
- Extract key details such as dates, amounts, GSTIN, PAN, and vendor information using OCR.
- OCR is powered by **Tesseract**; non‑image formats fall back to a simple placeholder message in this MVP.

### 2. Business & Document Management
- Create and manage businesses.
- Associate uploaded documents with a business.
- View documents, OCR text, and extracted line items for each business.
- See basic summaries of income, expenses, and GST aggregates per business.

### 3. Ledger & AI Roadmap (Planned / Partially Implemented)
- Core ledger models and services exist under `apps/ledger` for double‑entry vouchers and account balances.
- AI bridge and ingestion services under `apps/ai_bridge` and `apps/ingestion` will eventually:
  - Turn uploaded documents into draft vouchers.
  - Suggest ledger accounts and tax breakdowns automatically.
- These modules are **work in progress** and not yet wired into the main UI.

---

## Tech Stack
- **Backend:** Python, Django  
- **Database:** SQLite (MVP) via Django ORM  
- **OCR:** Tesseract  
- **Frontend:** Django templates (HTML/CSS)  

---

## Quick Start (Local)

### 1. Clone the repository

```bash
git clone https://github.com/YVK49/AI-based-accounting-system.git
cd AI-based-accounting-system
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```bash
python -m venv venv
venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Tesseract OCR (required for image OCR)

- **Ubuntu (example):**

  ```bash
  sudo apt update
  sudo apt install -y tesseract-ocr
  ```

- **Windows / macOS:**  
  Install Tesseract from the official binaries for your OS, and ensure `tesseract` is on your `PATH`.  
  If Tesseract is missing, uploads will succeed but OCR text will fall back to a placeholder.

### 5. Apply migrations

```bash
python manage.py migrate
```

### 6. Run the development server

```bash
python manage.py runserver
```

Then open `http://127.0.0.1:8000/` in your browser.

High‑level flows in the current UI:
- Sign up and log in.
- Create a business.
- Upload documents for that business.
- View documents and extracted text/line items.

---

## Contribution Notes

- Prefer creating feature branches from `main`:

  ```bash
  git checkout -b feature/your-feature-name
  ```

- Open a Pull Request on GitHub (`YVK49/AI-based-accounting-system`) for review before merging to `main`.

---

## Support

- **GitHub Issues:** `https://github.com/YVK49/AI-based-accounting-system/issues`

---

## License

This project is licensed under the Apache 2.0 License. See the `LICENSE` file for details.
