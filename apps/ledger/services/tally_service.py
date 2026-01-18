import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
from datetime import datetime
from django.utils import timezone
from ..models import Voucher, JournalEntry

class TallyExportService:
    """
    Elite CA-Grade Tally Automation Service.
    Produces 100% Audit-ready XML compatible with TallyPrime / ERP 9.
    """

    @classmethod
    def generate_voucher_xml(cls, voucher: Voucher):
        """
        Generates XML for a single voucher in Tally format.
        """
        tally_date = voucher.date.strftime('%Y%m%d')
        
        # Envelope & Header (Tally Discovery Protocol)
        envelope = ET.Element('ENVELOPE')
        header = ET.SubElement(envelope, 'HEADER')
        ET.SubElement(header, 'TALLYREQUEST').text = 'Import Data'
        
        body = ET.SubElement(envelope, 'BODY')
        import_data = ET.SubElement(body, 'IMPORTDATA')
        request_desc = ET.SubElement(import_data, 'REQUESTDESC')
        ET.SubElement(request_desc, 'REPORTNAME').text = 'Vouchers'
        
        request_data = ET.SubElement(import_data, 'REQUESTDATA')
        tally_msg = ET.SubElement(request_data, 'TALLYMESSAGE', {'xmlns:UDF': 'TallyUDF'})
        
        # Voucher Element (GAAP-Compliant Mapping)
        vch = ET.SubElement(tally_msg, 'VOUCHER', {
            'VCHTYPE': voucher.voucher_type,
            'ACTION': 'Create',
            'OBJVIEW': 'Accounting Voucher View'
        })
        
        ET.SubElement(vch, 'DATE').text = tally_date
        ET.SubElement(vch, 'VOUCHERTYPENAME').text = voucher.voucher_type
        ET.SubElement(vch, 'VOUCHERNUMBER').text = xml_escape(voucher.voucher_number)
        
        # Elite CFO Narration (Standard 4: Audit Accountability)
        narration = voucher.narration or "Automated CFO Sync"
        ET.SubElement(vch, 'NARRATION').text = xml_escape(narration)
        ET.SubElement(vch, 'ISOPTIONAL').text = 'No'
        ET.SubElement(vch, 'EFFECTIVEDATE').text = tally_date
        
        # Ledger Entries (Double-Entry Integrity)
        for entry in voucher.entries.all():
            ledger_entry = ET.SubElement(vch, 'ALLLEDGERENTRIES.LIST')
            ET.SubElement(ledger_entry, 'LEDGERNAME').text = xml_escape(entry.account.name)
            
            # Tally Standard Signage: Dr is Deemed Positive 'Yes'
            is_debit = entry.debit > 0
            ET.SubElement(ledger_entry, 'ISDEEMEDPOSITIVE').text = 'Yes' if is_debit else 'No'
            
            # Tally XML Math: Dr is Negative (-), Cr is Positive (+) in <AMOUNT>
            amount = -entry.debit if is_debit else entry.credit
            ET.SubElement(ledger_entry, 'AMOUNT').text = f"{amount:.2f}"
            
            # Bill Allocations (Statutory Payable/Receivable Tracking)
            if entry.ref_type or (entry.account.group.name in ['Sundry Creditors', 'Sundry Debtors']):
                bill_alloc = ET.SubElement(ledger_entry, 'BILLALLOCATIONS.LIST')
                ET.SubElement(bill_alloc, 'NAME').text = xml_escape(entry.ref_number or voucher.voucher_number)
                ET.SubElement(bill_alloc, 'BILLTYPE').text = cls._map_ref_type(entry.ref_type or 'NEW')
                ET.SubElement(bill_alloc, 'AMOUNT').text = f"{amount:.2f}"

            # Bank Allocations (Banking Recon Compatibility)
            if voucher.utr_number and (entry.account.classification == 'ASSET' and 'Bank' in entry.account.name):
                bank_alloc = ET.SubElement(ledger_entry, 'BANKALLOCATIONS.LIST')
                ET.SubElement(bank_alloc, 'DATE').text = tally_date
                ET.SubElement(bank_alloc, 'INSTRUMENTNUMBER').text = xml_escape(voucher.utr_number)
                ET.SubElement(bank_alloc, 'TRANSACTIONTYPE').text = 'Inter Bank Transfer'
                ET.SubElement(bank_alloc, 'AMOUNT').text = f"{amount:.2f}"

        return ET.tostring(envelope, encoding='unicode')

    @staticmethod
    def _map_ref_type(ref_type):
        mapping = {
            'NEW': 'New Ref',
            'AGST': 'Against Ref',
            'ADV': 'Advance',
            'ON_ACC': 'On Account'
        }
        return mapping.get(ref_type, 'On Account')

    @classmethod
    def export_business_vouchers(cls, business, start_date=None, end_date=None):
        """
        Generates a full Tally XML for all vouchers of a business.
        """
        vouchers = Voucher.objects.filter(business=business, is_draft=False)
        if start_date:
            vouchers = vouchers.filter(date__gte=start_date)
        if end_date:
            vouchers = vouchers.filter(date__lte=end_date)
            
        envelope = ET.Element('ENVELOPE')
        header = ET.SubElement(envelope, 'HEADER')
        ET.SubElement(header, 'TALLYREQUEST').text = 'Import Data'
        
        body = ET.SubElement(envelope, 'BODY')
        import_data = ET.SubElement(body, 'IMPORTDATA')
        request_desc = ET.SubElement(import_data, 'REQUESTDESC')
        ET.SubElement(request_desc, 'REPORTNAME').text = 'Vouchers'
        
        request_data = ET.SubElement(import_data, 'REQUESTDATA')
        
        for voucher in vouchers:
            tally_msg = ET.SubElement(request_data, 'TALLYMESSAGE', {'xmlns:UDF': 'TallyUDF'})
            cls._add_voucher_to_msg(tally_msg, voucher)
            
        return ET.tostring(envelope, encoding='unicode')

    @classmethod
    def _add_voucher_to_msg(cls, tally_msg, voucher):
        tally_date = voucher.date.strftime('%Y%m%d')
        vch = ET.SubElement(tally_msg, 'VOUCHER', {
            'VCHTYPE': voucher.voucher_type,
            'ACTION': 'Create',
            'OBJVIEW': 'Accounting Voucher View'
        })
        
        ET.SubElement(vch, 'DATE').text = tally_date
        ET.SubElement(vch, 'VOUCHERTYPENAME').text = voucher.voucher_type
        ET.SubElement(vch, 'VOUCHERNUMBER').text = xml_escape(voucher.voucher_number)
        
        # Elite CFO Narration
        narration = voucher.narration or "Automated CFO Sync"
        ET.SubElement(vch, 'NARRATION').text = xml_escape(narration)
        ET.SubElement(vch, 'ISOPTIONAL').text = 'No'
        ET.SubElement(vch, 'EFFECTIVEDATE').text = tally_date
        
        for entry in voucher.entries.all():
            ledger_entry = ET.SubElement(vch, 'ALLLEDGERENTRIES.LIST')
            ET.SubElement(ledger_entry, 'LEDGERNAME').text = xml_escape(entry.account.name)
            
            is_debit = entry.debit > 0
            ET.SubElement(ledger_entry, 'ISDEEMEDPOSITIVE').text = 'Yes' if is_debit else 'No'
            
            amount = -entry.debit if is_debit else entry.credit
            ET.SubElement(ledger_entry, 'AMOUNT').text = f"{amount:.2f}"
            
            if entry.ref_type or (entry.account.group.name in ['Sundry Creditors', 'Sundry Debtors']):
                bill_alloc = ET.SubElement(ledger_entry, 'BILLALLOCATIONS.LIST')
                ET.SubElement(bill_alloc, 'NAME').text = xml_escape(entry.ref_number or voucher.voucher_number)
                ET.SubElement(bill_alloc, 'BILLTYPE').text = cls._map_ref_type(entry.ref_type or 'NEW')
                ET.SubElement(bill_alloc, 'AMOUNT').text = f"{amount:.2f}"

            if voucher.utr_number and (entry.account.classification == 'ASSET' and 'Bank' in entry.account.name):
                bank_alloc = ET.SubElement(ledger_entry, 'BANKALLOCATIONS.LIST')
                ET.SubElement(bank_alloc, 'DATE').text = tally_date
                ET.SubElement(bank_alloc, 'INSTRUMENTNUMBER').text = xml_escape(voucher.utr_number)
                ET.SubElement(bank_alloc, 'TRANSACTIONTYPE').text = 'Inter Bank Transfer'
                ET.SubElement(bank_alloc, 'AMOUNT').text = f"{amount:.2f}"
