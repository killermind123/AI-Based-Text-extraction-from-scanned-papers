import re
from datetime import datetime


def clean_currency(value):
    """Clean and format currency values"""
    if not value:
        return None
    # Remove everything except digits, dots, commas
    cleaned = re.sub(r'[^\d.,]', '', str(value))
    return cleaned if cleaned else None


def clean_date(value):
    """Try to parse and standardise dates"""
    if not value:
        return None

    formats = [
        "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d",
        "%d-%m-%Y", "%d/%m/%y", "%m/%d/%y"
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


def postprocess_fields(fields):
    """
    Clean and format all extracted fields.
    Input:  dict of raw field_name → field_value
    Output: dict of cleaned field_name → field_value
    """
    cleaned = {}

    for field_name, field_value in fields.items():

        if field_name in ["total", "subtotal", "tax", "amount"]:
            cleaned[field_name] = clean_currency(field_value)

        elif field_name in ["date", "invoice_date", "due_date"]:
            cleaned[field_name] = clean_date(field_value)

        elif field_name in ["address", "signature"]:
            cleaned[field_name] = clean_text(field_value)

        else:
            cleaned[field_name] = clean_text(field_value)

    # Remove None values
    cleaned = {k: v for k, v in cleaned.items() if v is not None}

    return cleaned