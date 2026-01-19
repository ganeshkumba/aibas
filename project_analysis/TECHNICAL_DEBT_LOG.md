# 📉 Technical Debt & Roadmap
Tracking unresolved issues and future engineering requirements.

## I. Known Constraints
1. **API Quota (Critical):** Gemini 1.5 Free Tier is limited to 20 requests/day.
   - *Fix:* Link Google Cloud billing to enable 2,000 RPM.
2. **Database Engine:** Currently using SQLite for MVP.
   - *Fix:* Migrate to PostgreSQL for production concurrency and row-level locking.
3. **Background Tasks:** Document processing is currently synchronous.
   - *Fix:* Implement Celery + Redis for asynchronous background processing of large bank statements.

## II. Future Roadmap (The "Audit Master" Suite)
| Target | Description | Priority |
| :--- | :--- | :--- |
| **GSTR-2B Recon** | Match AI-scanned documents against GST portal JSON files. | HIGH |
| **Regional OCR** | Support for Hindi, Gujarati, and Tamil handwritten receipts. | MEDIUM |
| **PWA Mobile** | A mobile-first interface for field-upload of small receipts. | MEDIUM |
| **Direct Tally Sync** | Live API push to TallyPrime bypassing XML files. | LOW |

## III. Security Audit
- [x] Email-based JWT-ready Authentication.
- [ ] Row-level security for multi-tenant business data.
- [ ] Encryption at rest for uploaded financial IDs/PAN cards.
