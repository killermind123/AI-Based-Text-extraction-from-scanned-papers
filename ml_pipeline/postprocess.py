import re
from datetime import datetime


def clean_currency(value):
    """Clean and validate currency values"""
    if not value:
        return None
    
    # Remove currency symbols and spaces
    cleaned = re.sub(r'[^\d.,]', '', str(value))
    
    # Must contain a decimal point and be reasonable length
    if not cleaned:
        return None
    
    # Reject if too long (probably not a price)
    if len(cleaned.replace('.', '').replace(',', '')) > 8:
        return None
        
    # Must look like a number
    try:
        float(cleaned.replace(',', ''))
        return cleaned
    except ValueError:
        return None


def clean_date(value):
    """Try to parse and standardise dates"""
    if not value:
        return None

    formats = [
        "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d",
        "%d-%m-%Y", "%d/%m/%y", "%m/%d/%y",
        "%d-%m-%y", "%Y/%m/%d"
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return value.strip()


def clean_text(value):
    """Clean general text fields"""
    if not value:
        return None
    return " ".join(str(value).split()).strip()


def is_valid_total(value):
    """
    Check if extracted value looks like a real total.
    Rejects phone numbers, IDs etc.
    """
    if not value:
        return False

    # Remove currency symbols
    cleaned = re.sub(r'[^\d.,]', '', str(value))

    if not cleaned:
        return False

    # Phone numbers are usually 10+ digits with no decimal
    digits_only = re.sub(r'[^\d]', '', cleaned)
    if len(digits_only) > 7 and '.' not in cleaned:
        return False

    # Must be a valid number
    try:
        amount = float(cleaned.replace(',', ''))
        # Reasonable price range
        if amount < 0 or amount > 999999:
            return False
        return True
    except ValueError:
        return False


def postprocess_fields(fields):
    """
    Clean and validate all extracted fields.
    """
    cleaned = {}

    for field_name, field_value in fields.items():

        if field_name in ["total", "subtotal", "tax", "amount"]:
            val = clean_currency(field_value)
            if val and is_valid_total(val):
                cleaned[field_name] = val

        elif field_name in ["date", "invoice_date", "due_date"]:
            val = clean_date(field_value)
            if val:
                cleaned[field_name] = val

        elif field_name in ["address", "signature"]:
            val = clean_text(field_value)
            if val:
                cleaned[field_name] = val

        else:
            val = clean_text(field_value)
            if val:
                cleaned[field_name] = val

    # Remove None values
    cleaned = {k: v for k, v in cleaned.items() if v is not None}

    return cleaned