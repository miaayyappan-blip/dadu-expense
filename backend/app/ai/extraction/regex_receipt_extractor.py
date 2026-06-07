import re
from datetime import datetime

from app.models.expense import ExpenseCategory


def extract_receipt_regex(text: str):
    result = {
        "amount": None,
        "category": None,
        "description": None,
        "merchant": None,
        "date": None,
        "items_detected": 0,
        "is_partial_receipt": False,
        "extraction_notes": "regex extraction",
    }


    # Amount
    patterns = [
        r"grand\s*total.*?(\d+\.\d+)",
        r"total\s*amount.*?(\d+\.\d+)",
        r"bill\s*amount.*?(\d+\.\d+)",
        r"net\s*amount.*?(\d+\.\d+)",
    ]

    for p in patterns:
        match = re.search(p, text, re.I | re.S)
        if match:
            result["amount"] = float(match.group(1))
            break

    # Date
    date_match = re.search(
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        text
    )

    if date_match:
        try:
            result["date"] = datetime.strptime(
                date_match.group(1),
                "%d/%m/%Y"
            ).date()
        except:
            pass

    text_lower = text.lower()

    # Merchant + Category

    if "indianoil" in text_lower or "petrol" in text_lower:
        result["merchant"] = "Indian Oil"
        result["category"] = ExpenseCategory.TRANSPORT
        result["description"] = "Fuel purchase"

    elif "bikano" in text_lower:
        result["merchant"] = "Bikano's"
        result["category"] = ExpenseCategory.FOOD
        result["description"] = "Restaurant meal"

    elif "subway" in text_lower:
        result["merchant"] = "Subway"
        result["category"] = ExpenseCategory.FOOD
        result["description"] = "Restaurant meal"

    return result