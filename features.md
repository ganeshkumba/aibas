# Enterprise Financial OS: AI-Based Accounting System
**Project Feature Documentation**

## 1. AI-Autonomous Ingestion Pipeline
The "First-Mile" of the ecosystem, responsible for turning unstructured physical artifacts into structured financial data.
*   **Multimodal OCR & Vision**: Dual-layer system utilizing Tesseract for local scanned PDFs and Google Gemini Vision for high-fidelity extraction of complex tables.
*   **Automatic Document Classification**: Real-time categorization of artifacts into `Receipt/Invoice`, `Bank Statement`, or `Statutory Document`.
*   **MSME Threshold Detection**: Specialized logic to detect Udyam registration and enforce Section 43B(h) of the Income Tax Act (45-day payment tracking).
*   **B2B Identity Mapping**: Automatically compares the business GSTIN with the document to verify Input Tax Credit (ITC) eligibility.

## 2. Double-Entry Bookkeeping Engine (GAP-Compliant)
A high-performance engine engineered for strict financial accuracy and Tally-level robustness.
*   **Tally-Style Voucher Matrix**: Supports `Sales`, `Purchase`, `Payment`, `Receipt`, `Contra`, and `Journal` vouchers.
*   **Automated Ledger Bridging**: One-click conversion of AI-extracted line items into double-entry journal entries.
*   **Idempotency & Deduplication**: SHA-256 fingerprinting of transactions to prevent duplicate voucher registry (e.g., REC/0024 collisions).
*   **Financial Year Lockdown**: Prevents modification of records in closed periods to maintain audit integrity.

## 3. Forensic Shield & Security Hub
Advanced technical auditing and fraud detection mechanics.
*   **Metadata Triangulation**: Analyzes PDF `Producer` and `Author` strings to catch internally manipulated invoices.
*   **IP Geolocation Tracking**: Monitors document upload sources to flag anomalous activity from unusual locations.
*   **Immutable Hash-Chaining**: Every audit-level action is cryptographically chained to the previous entry, making back-end database tampering detectable.
*   **Identity Protection**: PBKDF2-SHA256 password hashing and business-level isolated data vaults.

## 4. Financial Intelligence HUD
Real-time reports translated into actionable business intelligence.
*   **"Human-Readable" P&L**: Modernized Profit & Loss statement with gamified efficiency scores (1-10) and "Major Cash Drain" identification.
*   **Operating Efficiency Analysis**: Dynamic progress bars visualizing the ratio of Revenue Flow vs. Expense Burn.
*   **Interactive Velocity Graphs**: Real-time line charts showing financial inflow/outflow trends over a 6-week rolling window.
*   **Equity/Worth Monitor**: Live Balance Sheet tracking with automated health checks for negative equity.

## 5. Inventory Intelligence
A comprehensive stock management and valuation system.
*   **Portfolio Valuation Engine**: Real-time calculation of inventory value based on FIFO/Weighted Average principles.
*   **Liquidity Pulse Bar**: Visualizes the stock turnover ratio to identify stagnant capital.
*   **Low-Stock Forensic Alerts**: Automated triggers for items falling below safety levels, integrated into the Forensic Dashboard.
*   **Audit Movement Trail**: Granular logging of every unit movement (IN/OUT) with timestamped traceability.

## 6. Amortization Engine (Deferred Recognition)
Enforces the "Matching Principle" for professional accounting standards.
*   **Automated Prepaid Asset Release**: Spreads large payments (e.g., Insurance, SaaS) over multiple periods.
*   **Recognition Stream Logs**: Real-time tracking of what has been recognized in P&L vs. what is still deferred on the Balance Sheet.
*   **Audit-Locked Cycles**: Each monthly release is cryptographically tied to the parent artifact for immutable traceability.

## 7. Intercompany Control Tower
The orchestration layer for organizations with multiple legal entities.
*   **Organizational Hierarchy Mapping**: Tiered visualization of Parent-Subsidiary structures with gradient flow indicators.
*   **Symmetry Verification**: Logic engine that ensures a `Payable` in the holding company matches a `Receivable` in the target subsidiary.
*   **Consolidation Elimination**: Automatically flags intercompany flux for audit elimination during group reports.

## 8. High-Fidelity UI/UX System
A premium design language inspired by modern FinTech standards.
*   **Shadcn Components**: Pixel-perfect inputs, tables, tags, and checkboxes built with Vanilla CSS and Tailwind utility classes.
*   **Neon Aura Cursor**: A high-performance cyan glow that shifts to magenta on interaction, providing reactive visual feedback.
*   **Zero-Scroll Engineering**: High-density form layouts optimized to fit entirely above the fold for maximum user focus.
*   **Glassmorphism & Dark Mode**: Sophisticated translucent layers and a deep carbon palette for reduced eye strain and a "State-of-the-Art" aesthetic.
