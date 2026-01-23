import datetime
import logging
from decimal import Decimal
from django.db import transaction, models
from apps.ledger.models import Voucher, JournalEntry, Account, FinancialYear, VoucherType, AccountGroup
from apps.ledger.services.ledger_service import LedgerService
from core.models import Document, ExtractedLineItem, Business
from apps.inventory.services.inventory_service import InventoryAutomationService


logger = logging.getLogger(__name__)

class AutomationService:
    """
    CA-Grade Automation Service.
    Converts raw documents/statements into GAAP-compliant vouchers.
    """
    VOUCHER_ALLOWED_GROUPS = {
        VoucherType.PURCHASE: ['Indirect Expenses', 'Direct Expenses', 'Fixed Assets', 'Duties & Taxes', 'Sundry Creditors'],
        VoucherType.SALES: ['Indirect Incomes', 'Direct Incomes', 'Duties & Taxes', 'Sundry Debtors'],
        VoucherType.PAYMENT: ['Indirect Expenses', 'Direct Expenses', 'Sundry Creditors', 'Bank Accounts', 'Cash-in-hand', 'Duties & Taxes'],
        VoucherType.RECEIPT: ['Indirect Incomes', 'Direct Incomes', 'Sundry Debtors', 'Bank Accounts', 'Cash-in-hand']
    }

    @staticmethod
    def normalize_ledger_name(name):
        """
        SECTION 2.1: Naming Conventions Standardization
        Ensures Proper Case, removes extra spaces, and standardizes terminology.
        Includes "Self-Healing" for common typos.
        """
        if not name:
            return "General Ledger"
        
        # 0. Common Typo Correction Map (Mistake 1.1 / 2.1)
        typo_map = {
            'COOUD': 'CLOUD',
            'SHIPING': 'SHIPPING',
            'COURIER / SHIPPING': 'COURIER/SHIPPING',
            'OFFICE SUPPLIE': 'OFFICE SUPPLIES',
            'STATIONARY': 'STATIONERY',
            'CONSLTING': 'CONSULTING',
            'ADVERTISMENT': 'ADVERTISEMENT',
            'SUBSCRIPTON': 'SUBSCRIPTION',
            'RECIEPT': 'RECEIPT'
        }
        
        # Clean extra spaces and convert to upper for map check
        clean_name = " ".join(name.split()).upper()
        
        # Apply typo corrections (Partial or Full)
        for typo, correct in typo_map.items():
            if typo in clean_name:
                clean_name = clean_name.replace(typo, correct)
        
        # 1. Standardize separators (e.g. " / " -> "/")
        clean_name = clean_name.replace(" / ", "/").replace(" - ", "-")
        
        # 2. Handle Proper Case but keep acronyms uppercase
        uppercases = ['GST', 'TDS', 'AWS', 'UTR', 'IGST', 'CGST', 'SGST', 'ITC', 'PAN', 'MSME', 'HDFC', 'ICICI', 'SBI']
        words = clean_name.split()
        normalized_words = []
        for word in words:
            # Strip common punctuation for keyword check, but keep it in the name
            punc_prefix = ""
            punc_suffix = ""
            while word and word[0] in '()[]/.-':
                punc_prefix += word[0]
                word = word[1:]
            while word and word[-1] in '()[]/.-':
                punc_suffix += word[-1]
                word = word[:-1]
                
            clean_word = word.upper()
            if clean_word in uppercases:
                normalized_words.append(f"{punc_prefix}{word.upper()}{punc_suffix}")
            else:
                normalized_words.append(f"{punc_prefix}{word.capitalize()}{punc_suffix}")
        
        normalized_name = " ".join(normalized_words)
        
        # Consistency Check: Append 'Expense' if missing from common indirect accounts (Mistake 2.2)
        if any(k in normalized_name.upper() for k in ['OFFICE SUPPLIES', 'SOFTWARE', 'CLOUD SUBSCRIPTION']) and 'EXPENSE' not in normalized_name.upper():
             normalized_name += " Expense"
             
        return normalized_name.strip()

    @staticmethod
    def get_or_create_default_account(business, name, group_name=None, voucher_type=None):
        """
        Automated Ledger Provisioning Engine (SECTION 1 & 2)
        """
        name = AutomationService.normalize_ledger_name(name)
        
        # 1. Self-Healing Search: If account exists in ANY group, reuse it
        # This prevents "Same Account in Multiple Groups" (Mistake 2.3)
        existing = Account.objects.filter(business=business, name__iexact=name).first()
        if existing:
            return existing

        # 2. Advanced Group Inference (Mistake 1.1 - 1.5)
        if not group_name:
            n_upper = name.upper()
            if any(k in n_upper for k in ['RENT', 'SALARY', 'WAGES', 'SUPPLIES', 'REPAIR', 'FEES', 'ADVERT', 'CHARGES', 'SUBSCRIPTION']):
                group_name = "Indirect Expenses"
            elif any(k in n_upper for k in ['BANK', 'CASH', 'HDFC', 'ICICI', 'PETTY']):
                group_name = "Bank Accounts"
            elif any(k in n_upper for k in ['SALES', 'INTEREST INCOME', 'REVENUE']):
                group_name = "Indirect Incomes"
            else:
                group_name = "Indirect Expenses" # Safe default for unknowns

        # Rule 1 Check: Ensure the ledger group is valid for this voucher type
        if voucher_type and voucher_type in AutomationService.VOUCHER_ALLOWED_GROUPS:
            allowed = AutomationService.VOUCHER_ALLOWED_GROUPS[voucher_type]
            if not any(a in group_name for a in allowed):
                logger.warning(f"VOUCHER MISMATCH: Group '{group_name}' not allowed for {voucher_type}. Correcting...")
                if voucher_type == VoucherType.PURCHASE and 'INCOME' in group_name.upper():
                    group_name = 'Indirect Expenses'
                elif voucher_type == VoucherType.SALES and 'EXPENSE' in group_name.upper():
                    group_name = 'Indirect Incomes'

        group = AccountGroup.objects.filter(business=business, name=group_name).first()
        if not group:
            classification = 'EXPENSE'
            gn_upper = group_name.upper()
            if 'INCOME' in gn_upper: classification = 'INCOME'
            elif any(k in gn_upper for k in ['ASSET', 'BANK', 'CASH', 'DEBTOR']): classification = 'ASSET'
            elif any(k in gn_upper for k in ['LIABILITY', 'CREDITOR', 'TAXES', 'CAPITAL', 'PAYABLE']): classification = 'LIABILITY'
            
            group, _ = AccountGroup.objects.get_or_create(
                business=business, 
                name=group_name,
                defaults={'classification': classification, 'is_revenue_nature': 'Expense' in group_name or 'Income' in group_name}
            )
        
        account, _ = Account.objects.get_or_create(
            business=business,
            name=name,
            group=group,
            defaults={'classification': group.classification}
        )
        return account

    @classmethod
    @transaction.atomic
    def convert_document_to_voucher(cls, document: Document):
        logger.info(f"Starting Ledger Bridge for Doc {document.id} ({document.status})")
        if document.status not in ["processed", "ocr_complete"]:
            logger.warning(f"Doc {document.id} status is {document.status}, bypassing bridge.")
            return None

        lines = document.lines.all()
        if not lines.exists():
            logger.warning(f"No extracted lines found for Doc {document.id}. Bridge aborted.")
            return None

        doc_date = document.document_date or (lines[0].date if lines.exists() else None) or datetime.date.today()
        logger.info(f"Resolving Financial Year for date {doc_date}")
        
        fy = FinancialYear.objects.filter(
            business=document.business, start_date__lte=doc_date, end_date__gte=doc_date
        ).first()

        if not fy:
            logger.info("No active FY found, generating fallback FY.")
            from datetime import date
            if doc_date.month >= 4:
                start_date = date(doc_date.year, 4, 1)
                end_date = date(doc_date.year + 1, 3, 31)
            else:
                start_date = date(doc_date.year - 1, 4, 1)
                end_date = date(doc_date.year, 3, 31)
                
            fy, _ = FinancialYear.objects.get_or_create(
                business=document.business,
                start_date=start_date,
                end_date=end_date
            )

        if document.doc_type == 'bank':
            logger.info(f"Processing as Bank Statement for Doc {document.id}")
            vouchers = cls._process_bank_statement(document, fy, lines)
        else:
            logger.info(f"Processing as Invoice for Doc {document.id}")
            vouchers = cls._process_invoice(document, fy, lines)
            
        # Always run the reconciliation engine after new docs are added
        cls.reconcile_pending_payments(document.business)
        
        # INCREASED FUNCTIONALITY: Update Inventory
        try:
            InventoryAutomationService.update_stock_from_document(document)
        except Exception as e:
            logger.error(f"Inventory Update Failed: {e}")

        # GOD-MODE: Capture Report Snapshots
        try:
            LedgerService.generate_financial_snapshots(document.business, document=document)
        except Exception as e:
            logger.error(f"Snapshot Generation Failed: {e}")
            
        return vouchers

    @classmethod
    def _process_bank_statement(cls, document, fy, lines):
        """
        Processes Bank Statements with strict Payment logic.
        Ensures Bank/Cash is always the source for Payments (Rule 2).
        """
        vouchers_created = []
        bank_account = cls.get_or_create_default_account(document.business, "Main Bank Account", "Bank Accounts")

        # Master Alias System (Mapping common fragments to professional ledgers)
        master_alias = {
            'NARAYANA': 'Reliable Realty',
            'RELIABLE': 'Reliable Realty',
            'BANGALORE': 'Office Landlord',
            'KARNATAKA': 'Office Landlord',
            'AMAZON': 'Amazon Web Services',
            'AWS': 'Amazon Web Services'
        }

        for line in lines:
            # Determine direction: Debit = Payment, Credit = Receipt
            is_payment = (line.debit and line.debit > 0)
            amount = line.debit if is_payment else line.credit
            
            if not amount or amount <= 0:
                continue

            v_type = VoucherType.PAYMENT if is_payment else VoucherType.RECEIPT
            entries_data = []
            desc_upper = (line.vendor or "").upper() # Description from bank
            purpose_upper = (line.description or "").upper() # Purpose/AI summary
            suggested_acc = (line.ledger_account or "").upper()

            # --- START SMART RECONCILIATION ---
            party_account = None
            ref_info = {"type": "ON_ACC", "number": line.invoice_no or "BANK-REF"}

            # 1. Direct detection for Bank Fees/Interest (Mistake 5)
            if "CHARGE" in desc_upper or "CHARGE" in suggested_acc or "FEES" in desc_upper:
                party_account = cls.get_or_create_default_account(document.business, "Bank Charges", "Indirect Expenses", voucher_type=v_type)
            elif "INTEREST" in desc_upper or "INTEREST" in suggested_acc:
                if not is_payment:
                    party_account = cls.get_or_create_default_account(document.business, "Interest Income", "Indirect Incomes", voucher_type=v_type)
                else:
                    party_account = cls.get_or_create_default_account(document.business, "Interest Expense", "Indirect Expenses", voucher_type=v_type)
            
            # 2. Seek exact Bill match (Mistake 4)
            if not party_account:
                target_group = 'Sundry Creditors' if is_payment else 'Sundry Debtors'
                target_v_type = VoucherType.PURCHASE if is_payment else VoucherType.SALES
                
                # Look for exact amount match
                potential_match = JournalEntry.objects.filter(
                    account__business=document.business,
                    account__group__name__icontains=target_group.replace('s', ''),
                    credit=amount if is_payment else 0,
                    debit=amount if not is_payment else 0,
                    voucher__voucher_type=target_v_type
                ).select_related('account', 'voucher').last()

                # Rule B: TDS Detection (Mistake 3)
                # If no exact match, look for a match where (Amount / 0.9) or (Amount / 0.98) matches an invoice
                if not potential_match and not is_payment:
                    for rate in [Decimal('0.10'), Decimal('0.02'), Decimal('0.05')]:
                        gross_amount = (amount / (1 - rate)).quantize(Decimal('0.01'))
                        tds_match = JournalEntry.objects.filter(
                            account__business=document.business,
                            account__group__name__icontains='Sundry Debtors',
                            debit=gross_amount,
                            voucher__voucher_type=VoucherType.SALES
                        ).select_related('account', 'voucher').last()
                        
                        if tds_match:
                            logger.info(f"TDS RECEIVABLE DETECTED: Receipt {amount} matches gross invoice {gross_amount} (rate {rate*100}%)")
                            party_account = tds_match.account
                            ref_info = {"type": "AGST", "number": tds_match.voucher.voucher_number}
                            
                            # Add TDS entry
                            tds_val = gross_amount - amount
                            tds_rec_acc = cls.get_or_create_default_account(document.business, f"TDS Receivable @ {rate*100}%", "Current Assets")
                            entries_data.append({'account_id': tds_rec_acc.id, 'debit': tds_val, 'credit': 0})
                            amount = gross_amount # Adjust receipt amount to gross for balancing the entry
                            break

                if potential_match and not party_account:
                    party_account = potential_match.account
                    ref_info = {"type": "AGST", "number": potential_match.voucher.voucher_number}

            # 3. AI suggested category (Mistake 1)
            if not party_account and suggested_acc and "PENDING" not in suggested_acc:
                group = "Indirect Expenses" if is_payment else "Indirect Incomes"
                if "DEBTOR" in suggested_acc or "SALE" in suggested_acc: group = "Sundry Debtors"
                elif "CREDITOR" in suggested_acc or "PURCHASE" in suggested_acc: group = "Sundry Creditors"
                
                party_account = cls.get_or_create_default_account(document.business, line.ledger_account, group, voucher_type=v_type)

            # 4. Alias / Map Fallbacks
            if not party_account:
                for key, prof_name in master_alias.items():
                    if key in desc_upper:
                        party_account = cls.get_or_create_default_account(document.business, prof_name, 'Sundry Creditors', voucher_type=v_type)
                        break

            if not party_account:
                party_account = cls.get_or_create_default_account(
                    document.business, 
                    "Pending Classification", 
                    "Current Liabilities" if is_payment else "Current Assets",
                    voucher_type=v_type
                )

            # --- Persistence ---
            if is_payment:
                # Dr Party, Cr Bank
                entries_data.append({'account_id': party_account.id, 'debit': amount, 'credit': 0, 'ref_type': ref_info['type'], 'ref_number': ref_info['number']})
                entries_data.append({'account_id': bank_account.id, 'debit': 0, 'credit': amount})
            else:
                # Dr Bank, Cr Party (Receipt amount might have been adjusted for TDS above)
                actual_cash = line.credit # The real cash that hit the bank
                entries_data.append({'account_id': bank_account.id, 'debit': actual_cash, 'credit': 0})
                entries_data.append({'account_id': party_account.id, 'debit': 0, 'credit': amount, 'ref_type': ref_info['type'], 'ref_number': ref_info['number']})

            v_date = line.date or document.document_date or datetime.date.today()
            
            # SECTION: The "To" Constraint Automation (Rule 4)
            if is_payment:
                # Payment: Dr [Party] To [Bank]
                narration = f"Payment: Dr {party_account.name} To {bank_account.name} | {line.description or ''} | Ref: {line.invoice_no or 'N/A'}"
            else:
                # Receipt: Dr [Bank] To [Party]
                narration = f"Receipt: Dr {bank_account.name} To {party_account.name} | {line.description or ''} | Ref: {line.invoice_no or 'N/A'}"

            voucher_data = {
                'voucher_type': v_type,
                'date': v_date,
                'fy_id': fy.id,
                'narration': narration,
                'is_draft': True,
                'utr_number': line.invoice_no,
                'document_id': document.id
            }
            
            try:
                vch = LedgerService.create_voucher(document.business, voucher_data, entries_data)
                vouchers_created.append(vch)
                logger.info(f"Created Voucher {vch.voucher_number} for line {line.id}")
            except Exception as e:
                logger.error(f"Automation Bridge Failed for line {line.id}: {e}")

        return vouchers_created

    @classmethod
    def _process_invoice(cls, document, fy, lines):
        """
        Processes Invoices with professional CA Logic.
        Handles Alias mapping, GSTИН state-code anchor, and round-off.
        """
        vendor_name_raw = lines[0].vendor or "Generic Vendor"
        biz_name = (document.business.name or "").lower()
        biz_gstin = (document.business.gstin or "").upper()
        vendor_gstin = (lines[0].vendor_gstin or "").upper()

        # Master Alias System (Rule 1)
        master_alias = {
            'NARAYANA': 'Reliable Realty',
            'RELIABLE': 'Reliable Realty',
            'BANGALORE': 'Office Landlord',
            'KARNATAKA': 'Office Landlord',
            'AMAZON': 'Amazon Web Services',
            'AWS': 'Amazon Web Services'
        }
        
        v_date = document.document_date or datetime.date.today()
        vendor_name = vendor_name_raw
        for key, professional_name in master_alias.items():
            if key in vendor_name_raw.upper():
                vendor_name = professional_name
                break
        
        # 1. Transaction Direction (Purchase vs Sales)
        is_purchase = True
        if biz_gstin and vendor_gstin and biz_gstin == vendor_gstin:
            is_purchase = False
        elif biz_name and biz_name in vendor_name_raw.lower():
            is_purchase = False

        v_type = VoucherType.PURCHASE if is_purchase else VoucherType.SALES

        # 2. Total Calculation
        total_amount = sum(line.amount for line in lines if line.amount)
        if total_amount <= 0: 
            logger.warning(f"Total amount for Doc {document.id} is zero. Skipping voucher creation.")
            return None

        party_group = "Sundry Creditors" if is_purchase else "Sundry Debtors"
        party_account = cls.get_or_create_default_account(document.business, vendor_name, party_group, voucher_type=v_type)
        
        entries_data = []
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        all_gst_rates = set()

        for line in lines:
            if not line.amount or line.amount == 0: continue
            
            # --- Smart Ledger Mapping ---
            suggested_name = line.ledger_account or ""
            expense_group = "Indirect Expenses" if is_purchase else "Indirect Incomes"
            
            # Prevent direction mismatch (e.g. 'Rent Received' in a Purchase)
            if is_purchase and 'RECEIVED' in suggested_name.upper():
                suggested_name = suggested_name.upper().replace('RECEIVED', 'EXPENSE').title()
            elif not is_purchase and 'EXPENSE' in suggested_name.upper():
                suggested_name = suggested_name.upper().replace('EXPENSE', 'INCOME').title()

            direct_keywords = ['RAW MATERIAL', 'FREIGHT', 'CARRIAGE', 'MANUFACTURING', 'WAGES', 'DIRECT']
            desc_upper = (line.description or "").upper()
            if any(k in desc_upper for k in direct_keywords):
                expense_group = "Direct Expenses" if is_purchase else "Direct Incomes"
            
            expense_acc = cls.get_or_create_default_account(
                document.business, 
                suggested_name or ("General Purchase" if is_purchase else "General Sale"), 
                expense_group,
                voucher_type=v_type
            )
            
            # --- INTERCOMPANY SYMMETRY CHECK (GOD-MODE) ---
            # Ref: ERR-304, 316, 403
            sister_biz = Business.objects.filter(
                models.Q(gstin__iexact=vendor_gstin) | models.Q(name__icontains=vendor_name)
            ).exclude(id=document.business.id).first()
            
            if sister_biz and document.business.is_intercompany_enabled:
                logger.info(f"INTERCOMPANY DETECTED: {document.business.name} -> {sister_biz.name}")
                # We can add a specialized narration or flag
                # For now, we'll mark the document confidence higher and add a Forensic note
                document.is_suspicious = False # Trusting known sister companies
                document.accounting_logic += f"\n[Intercompany Sync]: Verified against sister entity {sister_biz.name}."
                document.save()

            # --- GST Logic ---
            gst_rate_str = (line.gst_rate or "0").replace('%', '').strip()
            try:
                gst_pct = Decimal(gst_rate_str)
            except:
                gst_pct = Decimal('0')
            
            if gst_pct > 0:
                all_gst_rates.add(f"{gst_pct}%")
            
            base_amount = (line.amount / (1 + (gst_pct/100))).quantize(Decimal('0.01'))
            tax_total = (line.amount - base_amount).quantize(Decimal('0.01'))

            if is_purchase:
                entries_data.append({'account_id': expense_acc.id, 'debit': base_amount, 'credit': 0})
                total_debit += base_amount
            else:
                entries_data.append({'account_id': expense_acc.id, 'debit': 0, 'credit': base_amount})
                total_credit += base_amount

            if tax_total > 0:
                # Rule D: The "Kachha" Bill / B2C vs B2B Detection
                # If my GSTIN is missing from the bill, ITC cannot be claimed. Transfer tax to expense.
                if is_purchase and not document.is_b2b:
                    logger.info(f"Doc {document.id}: 'Kachha' bill detected (B2C). Moving GST to Expense.")
                    # Find the last expense entry and add tax to it
                    for ent in reversed(entries_data):
                        if ent['account_id'] == expense_acc.id:
                            ent['debit'] += tax_total
                            total_debit += tax_total
                            break
                    continue # Skip Duties & Taxes entries

                # --- Rule 3: GST State-Code Anchor ---
                is_interstate = False
                if vendor_gstin and len(vendor_gstin) >= 2 and biz_gstin and len(biz_gstin) >= 2:
                    is_interstate = vendor_gstin[:2] != biz_gstin[:2]
                else:
                    # Fallback to Place of Supply string check
                    pos = (line.place_of_supply or "").strip().upper()
                    biz_state = (document.business.state or "").strip().upper()
                    if pos and biz_state and pos != biz_state:
                        is_interstate = True
                
                prefix = "Input" if is_purchase else "Output"
                
                if is_interstate:
                    tax_name = f"{prefix} IGST {gst_pct}%"
                    tax_acc = cls.get_or_create_default_account(document.business, tax_name, "Duties & Taxes", voucher_type=v_type)
                    if is_purchase:
                        entries_data.append({'account_id': tax_acc.id, 'debit': tax_total, 'credit': 0})
                        total_debit += tax_total
                    else:
                        entries_data.append({'account_id': tax_acc.id, 'debit': 0, 'credit': tax_total})
                        total_credit += tax_total
                else:
                    cgst_name = f"{prefix} CGST {(gst_pct/2).quantize(Decimal('0.1'))}%"
                    sgst_name = f"{prefix} SGST {(gst_pct/2).quantize(Decimal('0.1'))}%"
                    cgst_acc = cls.get_or_create_default_account(document.business, cgst_name, "Duties & Taxes", voucher_type=v_type)
                    sgst_acc = cls.get_or_create_default_account(document.business, sgst_name, "Duties & Taxes", voucher_type=v_type)
                    
                    # Rule C: Fractional GST Round-offs (1-paisa balancing)
                    half_tax = (tax_total / 2).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
                    other_half = tax_total - half_tax # Automatically catches the 1p difference
                    
                    if is_purchase:
                        entries_data.append({'account_id': cgst_acc.id, 'debit': half_tax, 'credit': 0})
                        entries_data.append({'account_id': sgst_acc.id, 'debit': other_half, 'credit': 0})
                        total_debit += tax_total
                    else:
                        entries_data.append({'account_id': cgst_acc.id, 'debit': 0, 'credit': half_tax})
                        entries_data.append({'account_id': sgst_acc.id, 'debit': 0, 'credit': other_half})
                        total_credit += tax_total

        # 3. Final Leg (Vendor/Customer)
        final_leg_amount = total_amount
        
        # Rule B: TDS Applicability (Section 194Q / 194J / 194I)
        tds_entry = None
        if is_purchase:
            items_desc = " ".join([l.description or "" for l in lines]).upper()
            suggested_ledgers = " ".join([l.ledger_account or "" for l in lines]).upper()
            
            tds_rate = None
            if "RENT" in items_desc or "RENT" in suggested_ledgers:
                if total_amount > 20000: # Simple monthly threshold check
                    tds_rate = Decimal('0.10') # 10% for Rent (typically 194I)
            elif "CONSULTANCY" in items_desc or "PROFESSIONAL" in items_desc or "LEGAL" in items_desc:
                if total_amount > 30000: # 194J threshold
                    tds_rate = Decimal('0.10') # 10%
            
            if tds_rate:
                tds_value = (total_amount * tds_rate).quantize(Decimal('0.01'))
                final_leg_amount = total_amount - tds_value
                
                tds_acc = cls.get_or_create_default_account(document.business, f"TDS Payable @ {tds_rate*100}%", "Duties & Taxes", voucher_type=v_type)
                tds_entry = {'account_id': tds_acc.id, 'debit': 0, 'credit': tds_value}
                logger.info(f"God-Level TDS detected: Deducting {tds_value} (rate {tds_rate*100}%)")

        if is_purchase:
            entries_data.append({'account_id': party_account.id, 'debit': 0, 'credit': final_leg_amount})
            total_credit += final_leg_amount
            if tds_entry:
                entries_data.append(tds_entry)
                total_credit += tds_entry['credit']
        else:
            entries_data.append({'account_id': party_account.id, 'debit': final_leg_amount, 'credit': 0})
            total_debit += final_leg_amount

        # 4. Professional Round-off Handling
        diff = (total_debit - total_credit).quantize(Decimal('0.01'))
        if abs(diff) > 0 and abs(diff) < 2: # Allow up to 2 INR rounding
            round_off_acc = cls.get_or_create_default_account(document.business, "Round Off", "Indirect Expenses", voucher_type=v_type)
            if diff > 0: # More Dr than Cr -> Need to add Cr
                 entries_data.append({'account_id': round_off_acc.id, 'debit': 0, 'credit': diff})
                 total_credit += diff
            else: # More Cr than Dr -> Need to add Dr
                 entries_data.append({'account_id': round_off_acc.id, 'debit': abs(diff), 'credit': 0})
                 total_debit += abs(diff)

        elif abs(diff) >= 2:
            logger.error(f"Imbalance too large for Doc {document.id}: {diff}")
            raise ValueError(f"High Math Variance: Dr({total_debit}) != Cr({total_credit}). Manual review required.")

        # 5. Voucher Persistence (CFO Standard Narration - Rule 4)
        tax_info = f"GST {', '.join(all_gst_rates)}" if all_gst_rates else "Non-GST"
        inv_no = document.document_number or "N/A"
        period = v_date.strftime("%b %Y")
        
        # SECTION: The "To" Constraint Automation (Rule 4)
        if is_purchase:
            # Purchase: Dr [Expenses] To [Vendor]
            summary_dr = ", ".join(all_gst_rates) if all_gst_rates else "Goods/Services"
            narration = f"Purchase: Dr {summary_dr} To {party_account.name} | Inv: {inv_no} | {period}"
        else:
            # Sales: Dr [Customer] To [Income]
            narration = f"Sales: Dr {party_account.name} To Revenue | Inv: {inv_no} | {period}"

        voucher_data = {
            'voucher_type': v_type,
            'date': v_date,
            'fy_id': fy.id,
            'narration': narration,
            'is_draft': True,
            'document_id': document.id
        }

        try:
            vch = LedgerService.create_voucher(document.business, voucher_data, entries_data)
            logger.info(f"Successfully created Voucher {vch.voucher_number} for Invoice Doc {document.id}")
            
            # --- START AMORTIZATION ENGINE (GOD-MODE) ---
            cls._apply_amortization_audit(vch, lines)
            
            return vch
        except Exception as e:
            logger.error(f"Voucher creation failed for Doc {document.id}: {e}")
            raise

    @classmethod
    def _apply_amortization_audit(cls, voucher, lines):
        """
        Scans for 'Annual', 'Subscription', or Date Ranges to trigger Matching Principle.
        Ref: ERR-101, 151, 202
        """
        from apps.ledger.models import AmortizationSchedule, AmortizationMovement
        
        desc = " ".join([l.description or "" for l in lines]).upper()
        keywords = ['ANNUAL', 'YEARLY', 'SUBSCRIPTION', '12 MONTH', 'RETAINER', 'INSURANCE']
        
        if any(k in desc for k in keywords) and voucher.total_amount > 1000:
            logger.info(f"Amortization Triggered for Voucher {voucher.voucher_number}")
            
            # Identify the expense entry
            expense_entry = voucher.entries.filter(debit__gt=0).exclude(account__group__name='Duties & Taxes').first()
            if not expense_entry: return

            # Resolve Asset Account (Prepaid)
            business = voucher.business
            original_acc = expense_entry.account
            prepaid_name = f"Prepaid {original_acc.name}"
            asset_acc = cls.get_or_create_default_account(business, prepaid_name, "Current Assets")
            
            # Move Debit from Expense to Asset
            expense_entry.account = asset_acc
            expense_entry.save()
            
            # Create Schedule
            periods = 12 # Default to 12 if 'Annual'
            if '3 YEAR' in desc: periods = 36
            elif 'MONTHLY' in desc: periods = 1 # Usually not amortized but kept for audit
            
            start_date = voucher.date
            # Simple month addition logic
            import datetime
            from dateutil.relativedelta import relativedelta
            end_date = start_date + relativedelta(months=periods-1)
            
            schedule = AmortizationSchedule.objects.create(
                business=business,
                voucher=voucher,
                asset_account=asset_acc,
                expense_account=original_acc,
                total_amount=voucher.total_amount,
                start_date=start_date,
                end_date=end_date,
                periods=periods
            )
            
            # Create Movements
            monthly_amt = (voucher.total_amount / periods).quantize(Decimal('0.01'))
            for i in range(periods):
                AmortizationMovement.objects.create(
                    schedule=schedule,
                    date=start_date + relativedelta(months=i),
                    amount=monthly_amt
                )
            
            logger.info(f"Generated {periods} amortization movements for {original_acc.name}")

    @classmethod
    def reconcile_pending_payments(cls, business):
        """
        Rule 4: Automated Reconciliation Engine.
        Finds 'Pending' entries and matches them to Invoices.
        """
        from apps.ledger.models import JournalEntry, VoucherType
        logger.info(f"Starting Reconciliation for {business.name}")
        
        # Search for any account containing 'Pending Classification'
        pending_entries = JournalEntry.objects.filter(
            account__name__icontains="Pending Classification",
            voucher__business=business
        ).select_related('voucher', 'account')
        
        matches_found = 0
        for entry in pending_entries:
            is_payment = entry.voucher.voucher_type == VoucherType.PAYMENT
            is_receipt = entry.voucher.voucher_type == VoucherType.RECEIPT
            
            if not (is_payment or is_receipt):
                continue

            # For Payments (Dr Pending), we seek a Purchase (Cr Party)
            # For Receipts (Cr Pending), we seek a Sale (Dr Party)
            amount = entry.debit if is_payment else entry.credit
            if not amount or amount <= 0:
                continue

            target_v_type = VoucherType.PURCHASE if is_payment else VoucherType.SALES
            target_group = 'Sundry Creditors' if is_payment else 'Sundry Debtors'
            
            # Match logic: Same amount AND check if vendor/customer name is in the narration
            narration = (entry.voucher.narration or "").upper()
            
            potential_matches = JournalEntry.objects.filter(
                account__business=business,
                account__group__name__icontains=target_group.replace('s', ''), # Handle Creditor/Creditors
                credit=amount if is_payment else 0,
                debit=amount if is_receipt else 0,
                voucher__voucher_type=target_v_type
            ).select_related('account', 'voucher')
            
            potential_match = None
            for pm in potential_matches:
                # If party name appears in narration, it's a high-confidence match
                if pm.account.name.upper() in narration:
                    potential_match = pm
                    break
            
            # Fallback: if only one match exists for this exact amount across all creditors/debtors
            if not potential_match and potential_matches.count() == 1:
                potential_match = potential_matches.first()
            
            if potential_match:
                logger.info(f"MATCH FOUND: {entry.voucher.voucher_type} {entry.voucher.id} matches {target_v_type} {potential_match.voucher.id}")
                
                with transaction.atomic():
                    # Re-map the pending entry to the actual vendor/customer
                    entry.account = potential_match.account
                    entry.ref_type = 'AGST'
                    entry.ref_number = potential_match.voucher.voucher_number
                    entry.save()
                    
                    # Update narration to reflect audit trail
                    entry.voucher.narration += f" | [RECONCILED to {potential_match.account.name}]"
                    entry.voucher.save()
                    matches_found += 1
                    
        return matches_found
