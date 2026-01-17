# AI-Based Accounting System - Code Review & Documentation

## ⚙️ Project Settings (`acctproj/settings.py`)

### `BASE_DIR`
- **What is it?**: The root directory of the project on the local file system.
- **Function**: Used by Django to locate templates, static files, and media directories. It serves as the starting point for all relative paths.

### `SECRET_KEY`
- **What is it?**: A unique master key used for cryptographic signing.
- **Security Note**: 
    - Used to sign session data, password reset tokens, and other security-sensitive information.
    - **Crucial**: Never share this key. If compromised, an attacker can hijack user sessions and impersonate users.
    - **Hardening**: Now loaded from the `.env` file for production safety.

### `AUTH_PASSWORD_VALIDATORS`
- **What is it?**: A set of rules used to ensure user passwords meet security standards.
- **Current Status**: Hardened to include:
    - `UserAttributeSimilarityValidator`: Prevents passwords similar to user info.
    - `MinimumLengthValidator`: Enforces a minimum length (currently 9 characters).
    - `CommonPasswordValidator`: Prevents easily guessable passwords.
    - `NumericPasswordValidator`: Disallows entirely numeric passwords.

### `AUTH_USER_MODEL`
- **What is it?**: Defines the custom user model for the project.
- **Value**: `'accounts.User'` (Points to the custom `User` model in `apps.accounts`).

### `AI_PROVIDER`
- **What is it?**: Configuration to switch between different AI extraction backends.
- **Options**: Currently set to `'mock'` for local testing. In production, this can be swapped to `'openai'`, `'anthropic'`, `'deepseek'`, or `'google'`.

---

## 🏗️ Core Data Models (`core/models.py`)

### `Business` Class
*Think of this as a "Company Profile".*

| Feature | Description |
| :--- | :--- |
| **Identity** | Name, PAN (Tax ID), and GSTIN. |
| **Financials** | Start and End dates for the financial year. |
| **Tracking** | `created_by` (Accountant) and `owner` (Client). |
| **Status** | Status filters: `onboarding`, `active`, `paused`, `closed`. |
| **Storage** | Uses `upload_to` to organize files by Business ID. |

### `Document` Class
*The "Digital Filing Cabinet" for receipts and invoices.*

**Key Tracking Fields:**
- `business` (Owner of the document)
- `uploaded_by` (User who submitted the file)
- `doc_type` (Receipt, Bank Statement, etc.)
- `document_number` (Reference/Invoice #)
- `is_processed` (Flag for AI completion)
- `ocr_text` (Raw text extracted by AI)

### `ExtractedLineItem` Class
*A detailed breakdown of data read by the AI.*

**Available Data Points:**
- **Relationship**: Links back to the original `Document`.
- **Details**: Date, Vendor, Amount, Tax Amount.
- **Accounting**: `ledger_account` (Suggested category).
- **Verification**: `is_verified` (Human verification status).

---

## 🛠️ Administrative Interface (`core/admin.py`)

### Custom Filters
- **`BusinessFilter`**: Filter transactions and documents by selecting a specific business.
- **`DocumentFilter`**: Filter by document types and processing status.
- **`LineItemBusinessFilter`**: Isolate line items belonging to a particular business.

### Admin Modules
1.  **Business Admin**: Displays ID, Name, Owner, and Status. Supports searching by PAN and GSTIN.
2.  **Document Admin**: Tracks uploads with autocomplete fields for Businesses and Users.
3.  **Line Item Admin**: Provides a verified/unverified toggle and ledger category filtering.

---

## 📝 Input Forms (`core/forms.py`)

### Business Management
- **`BusinessForm`**: Handles creation/editing of business profiles. Includes Regex validation for **PAN** and **GSTIN** formats.

### Document Handling
- **`DocumentUploadForm`**: Manages file uploads. Includes a **10MB size limit** validator to prevent server bloat.

### User Authentication
- **`SignUpForm`**: Extends `UserCreationForm` to include `full_name` and custom `email` validation.
- `LoginForm`: Standardizes authentication using Email as the primary identifier instead of a username.

---

## 🌐 Core Logic & Views (`core/views.py`)

### 🔑 User Authentication
Manages user sessions and secure access to the platform.

*   **`signup_view`**: Uses `SignUpForm`. Validates, saves, and automatically logs in new users. *Note: Exception handling needs to be implemented.*
*   **`login_view`**: Uses `LoginForm`. Standard email-based authentication. *Note: Exception handling needs to be implemented.*
*   **`logout_view`**: Terminates the user session and redirects to the login page.

### 🏢 Business Management
The central hub for managing company profiles and financial dashboards.

*   **`index` (Dashboard)**: The entry point. Retrieves all businesses created by the user, sorted by the most recent.
*   **`business_create`**: Uses `BusinessForm`. Handles the creation of new company profiles and links them to the logged-in user.
*   **`business_detail`**: The primary view for a specific company. Provides an AI-generated business summary and navigates to its documents.

### 📄 Document Processing
The "Smart" part of the application handling OCR and data extraction.

*   **`upload_document`**: 
    - Uses `DocumentUploadForm`.
    - **OCR Engine**: Automatically detects if the file is an image (`.png`, `.jpg`, `.jpeg`, etc.).
    - If valid, it runs **Tesseract OCR** to extract raw text.
    - If invalid or unsupported, it flags the status for the MVP.
    - Triggers the `process_document` function for background AI analysis.
*   **`documents_list`**: Provides a historical view of all documents uploaded for a business, sorted chronologically.
*   **`document_detail`**: A granular view of a single document, displaying both the original file and the specific line items extracted by the AI.
