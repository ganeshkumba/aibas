import logging
import datetime
from decimal import Decimal
from django.db import models
from apps.ledger.models import Account, AccountGroup, FinancialYear

logger = logging.getLogger(__name__)

# Master Alias System (Mapping common fragments to professional ledgers)
# Moved to a central registry to avoid redundancy in _process_bank_statement and _process_invoice
MASTER_ALIAS = {
    'NARAYANA': 'Reliable Realty',
    'RELIABLE': 'Reliable Realty',
    'BANGALORE': 'Office Landlord',
    'KARNATAKA': 'Office Landlord',
    'AMAZON': 'Amazon Web Services',
    'AWS': 'Amazon Web Services',
    'FLIPKART': 'Flipkart India',
    'ZOMATO': 'Zomato Limited',
    'SWIGGY': 'Bundl Technologies (Swiggy)',
    'AIRTEL': 'Bharti Airtel',
    'JIO': 'Reliance Jio',
}

TYPO_MAP = {
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

UPPERCASE_ACRONYMS = ['GST', 'TDS', 'AWS', 'UTR', 'IGST', 'CGST', 'SGST', 'ITC', 'PAN', 'MSME', 'HDFC', 'ICICI', 'SBI']

class LedgerCommonUtils:
    @staticmethod
    def normalize_ledger_name(name):
        if not name:
            return "General Ledger"
        
        # Clean extra spaces and convert to upper for map check
        clean_name = " ".join(name.split()).upper()
        
        # Apply typo corrections
        for typo, correct in TYPO_MAP.items():
            if typo in clean_name:
                clean_name = clean_name.replace(typo, correct)
        
        # Standardize separators
        clean_name = clean_name.replace(" / ", "/").replace(" - ", "-")
        
        # Handle Proper Case but keep acronyms uppercase
        words = clean_name.split()
        normalized_words = []
        for word in words:
            p_pref, p_suff = "", ""
            while word and word[0] in '()[]/.-': p_pref += word[0]; word = word[1:]
            while word and word[-1] in '()[]/.-': p_suff += word[-1]; word = word[:-1]
                
            if word.upper() in UPPERCASE_ACRONYMS:
                normalized_words.append(f"{p_pref}{word.upper()}{p_suff}")
            else:
                normalized_words.append(f"{p_pref}{word.capitalize()}{p_suff}")
        
        normalized_name = " ".join(normalized_words)
        
        # Consistency Check: Append 'Expense' if missing from common indirect accounts
        if any(k in normalized_name.upper() for k in ['OFFICE SUPPLIES', 'SOFTWARE', 'CLOUD SUBSCRIPTION']) and 'EXPENSE' not in normalized_name.upper():
             normalized_name += " Expense"
             
        return normalized_name.strip()

    @staticmethod
    def get_financial_year(business, date_obj):
        """Unifies FY resolution logic used across services."""
        fy = FinancialYear.objects.filter(
            business=business, start_date__lte=date_obj, end_date__gte=date_obj
        ).first()
        
        if not fy:
            if date_obj.month >= 4:
                start_date = datetime.date(date_obj.year, 4, 1)
                end_date = datetime.date(date_obj.year + 1, 3, 31)
            else:
                start_date = datetime.date(date_obj.year - 1, 4, 1)
                end_date = datetime.date(date_obj.year, 3, 31)
            
            fy, _ = FinancialYear.objects.get_or_create(
                business=business, start_date=start_date, end_date=end_date
            )
        return fy

    @staticmethod
    def resolve_party_by_alias(raw_name):
        if not raw_name: return None
        upper_name = raw_name.upper()
        for key, professional_name in MASTER_ALIAS.items():
            if key in upper_name:
                return professional_name
        return None
