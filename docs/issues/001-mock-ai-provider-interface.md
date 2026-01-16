## Issue: Fix mock AI provider to match `BaseAIProvider` interface

**Status:** Fixed  
**Area:** `apps/ai_bridge`  
**Type:** Bug

### What was broken

- `MockAIProvider` in `apps/ai_bridge/providers/mock_provider.py`:
  - Imported a non‑existent class `AIProvider` from `base.py`.
  - Exposed methods like `extract_invoice_data`, `classify_transaction`, and `generate_compliance_explanation`
    that did **not** match the expected `BaseAIProvider.extract(text: str) -> dict` interface.
- As a result, the mock provider could not be safely imported or used as a drop‑in replacement for a real AI provider.

### Fix implemented

- Updated `MockAIProvider` to:
  - Subclass `BaseAIProvider`.
  - Implement a single method:
    - `extract(text: str) -> dict`
  - Return deterministic, mock invoice data:
    - `vendor`, `invoice_no`, `date`, `total_amount`, `tax_amount`, `confidence`.

### Why this matters

- The mock provider can now be used in development and tests as a **fake AI engine**, without calling any external LLM.
- Future `AIService` code can rely on a consistent provider contract (`extract(text)`) for both:
  - Real providers (e.g. `OllamaProvider`).
  - Mock providers (e.g. `MockAIProvider`).

