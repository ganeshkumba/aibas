import xml.etree.ElementTree as ET
from datetime import datetime
from django.utils import timezone
from ..models import Voucher, JournalEntry

class TallyExportService:
    """
    Service to generate Tally-compatible XML for vouchers.
    """

    @staticmethod
    def generate_voucher_xml(voucher: Voucher):
        """
        Generates XML for a single voucher in Tally format.
        """
        tally_date = voucher.date.strftime('%Y%m%d')
        
        # Envelope & Header
        envelope = ET.Element('ENVELOPE')
        header = ET.SubElement(envelope, 'HEADER')
        ET.SubElement(header, 'TALLYREQUEST').text = 'Import Data'
        
        body = ET.SubElement(envelope, 'BODY')
        import_data = ET.SubElement(body, 'IMPORTDATA')
        request_desc = ET.SubElement(import_data, 'REQUESTDESC')
        ET.SubElement(request_desc, 'REPORTNAME').text = 'Vouchers'
        
        request_data = ET.SubElement(import_data, 'REQUESTDATA')
        tally_msg = ET.SubElement(request_data, 'TALLYMESSAGE', {'xmlns:UDF': 'TallyUDF'})
        
        # Voucher Element
        vch = ET.SubElement(tally_msg, 'VOUCHER', {
            'VCHTYPE': voucher.voucher_type,
            'ACTION': 'Create',
            'OBJVIEW': 'Accounting Voucher View'
        })
        
        ET.SubElement(vch, 'DATE').text = tally_date
        ET.SubElement(vch, 'VOUCHERTYPENAME').text = voucher.voucher_type
        ET.SubElement(vch, 'VOUCHERNUMBER').text = voucher.voucher_number
        ET.SubElement(vch, 'NARRATION').text = voucher.narration or ''
        ET.SubElement(vch, 'ISOPTIONAL').text = 'No'
        ET.SubElement(vch, 'EFFECTIVEDATE').text = tally_date
        
        # Ledger Entries (All-Ledger-Entries.List in Tally)
        for entry in voucher.entries.all():
            ledger_entry = ET.SubElement(vch, 'ALLLEDGERENTRIES.LIST')
            ET.SubElement(ledger_entry, 'LEDGERNAME').text = entry.account.name
            ET.SubElement(ledger_entry, 'ISDEEMEDPOSITIVE').text = 'Yes' if entry.debit > 0 else 'No'
            
            # Amount in Tally XML must be negative for Debit? 
            # Actually, Tally expects positive amounts and uses ISDEEMEDPOSITIVE 
            # BUT usually Debit is negative in XML for LedgerEntries.
            amount = entry.debit if entry.debit > 0 else -entry.credit
            ET.SubElement(ledger_entry, 'AMOUNT').text = str(amount)
            
            # Bill Allocations
            if entry.ref_type:
                bill_alloc = ET.SubElement(ledger_entry, 'BILLALLOCATIONS.LIST')
                ET.SubElement(bill_alloc, 'NAME').text = entry.ref_number or voucher.voucher_number
                ET.SubElement(bill_alloc, 'BILLTYPE').text = cls._map_ref_type(entry.ref_type)
                ET.SubElement(bill_alloc, 'AMOUNT').text = str(amount)

            # Bank Allocations (for UTR/Cheque)
            if voucher.utr_number and entry.account.group.classification == 'ASSET' and 'Bank' in entry.account.name:
                bank_alloc = ET.SubElement(ledger_entry, 'BANKALLOCATIONS.LIST')
                ET.SubElement(bank_alloc, 'DATE').text = tally_date
                ET.SubElement(bank_alloc, 'INSTRUMENTNUMBER').text = voucher.utr_number
                ET.SubElement(bank_alloc, 'TRANSACTIONTYPE').text = 'Inter Bank Transfer'
                ET.SubElement(bank_alloc, 'AMOUNT').text = str(amount)

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
        ET.SubElement(vch, 'VOUCHERNUMBER').text = voucher.voucher_number
        ET.SubElement(vch, 'NARRATION').text = voucher.narration or ''
        ET.SubElement(vch, 'ISOPTIONAL').text = 'No'
        ET.SubElement(vch, 'EFFECTIVEDATE').text = tally_date
        
        for entry in voucher.entries.all():
            ledger_entry = ET.SubElement(vch, 'ALLLEDGERENTRIES.LIST')
            ET.SubElement(ledger_entry, 'LEDGERNAME').text = entry.account.name
            ET.SubElement(ledger_entry, 'ISDEEMEDPOSITIVE').text = 'Yes' if entry.debit > 0 else 'No'
            
            amount = entry.debit if entry.debit > 0 else -entry.credit
            ET.SubElement(ledger_entry, 'AMOUNT').text = str(amount)
            
            if entry.ref_type:
                bill_alloc = ET.SubElement(ledger_entry, 'BILLALLOCATIONS.LIST')
                ET.SubElement(bill_alloc, 'NAME').text = entry.ref_number or voucher.voucher_number
                ET.SubElement(bill_alloc, 'BILLTYPE').text = cls._map_ref_type(entry.ref_type)
                ET.SubElement(bill_alloc, 'AMOUNT').text = str(amount)

            if voucher.utr_number and entry.account.group.classification == 'ASSET':
                bank_alloc = ET.SubElement(ledger_entry, 'BANKALLOCATIONS.LIST')
                ET.SubElement(bank_alloc, 'DATE').text = tally_date
                ET.SubElement(bank_alloc, 'INSTRUMENTNUMBER').text = voucher.utr_number
                ET.SubElement(bank_alloc, 'TRANSACTIONTYPE').text = 'Inter Bank Transfer'
                ET.SubElement(bank_alloc, 'AMOUNT').text = str(amount)
