import json
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import google.generativeai as genai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.core.config import settings
from app.models.expense import ExpenseCategory

logger = logging.getLogger(__name__)

# ── Receipt extraction system prompt ──────────────────────────────────────────
# Different from voice prompt because:
# 1. Receipts have TOTAL vs SUBTOTAL — always use the GRAND TOTAL
# 2. Merchant name is usually at the TOP of the receipt
# 3. Receipts often list multiple items — summarize, don't list
# 4. Date format varies wildly on receipts
# 5. Tax lines must NOT be added to the amount
RECEIPT_SYSTEM_PROMPT = """You are a receipt parsing engine. Extract structured expense data from OCR text of a receipt.

CRITICAL RULES:
1. Return ONLY valid JSON. No markdown, no explanation.
2. AMOUNT: Use the GRAND TOTAL or TOTAL AMOUNT only. Never use subtotals, tax amounts, or individual item prices.
3. If multiple totals exist, use the LARGEST final total (the one the customer actually paid).
4. MERCHANT: Extract the store/restaurant name, usually at the very top of the receipt.
5. DATE: The transaction date on the receipt. Format as YYYY-MM-DD.
6. DESCRIPTION: Summarize what was purchased in 3-10 words. Don't list every item.
7. If a field cannot be found reliably, return null. Never guess amounts.
8. Amounts must be numeric only (no currency symbols, no commas in the number).
9. Today's date for reference: {today}

CATEGORY MAPPING (use exactly these values):
- Food: restaurants, cafes, food delivery, groceries, supermarkets, bakeries, canteen
- Transport: fuel stations, parking, toll, taxi receipts, vehicle service
- Shopping: retail stores, clothing, electronics, department stores, online delivery
- Entertainment: movies, events, gaming, streaming service invoices
- Health: pharmacies, clinics, hospitals, diagnostic labs, optical stores
- Utilities: electricity bills, water bills, telecom, internet provider invoices
- Education: bookstores, stationery shops, course fee receipts
- Travel: hotels, resorts, airlines, travel agencies
- Other: anything that doesn't clearly fit the above

RECEIPT-SPECIFIC EXTRACTION NOTES:
- Lines like "SUBTOTAL", "TAX", "GST", "VAT", "SERVICE CHARGE", "DISCOUNT" are NOT the total
- The total is usually labeled: "TOTAL", "GRAND TOTAL", "AMOUNT DUE", "NET PAYABLE", "BILL AMOUNT"
- Ignore: barcodes, QR codes, loyalty points, store IDs, cashier names, table numbers
- If you see "CASH", "CARD", "UPI", "PAID" with an amount — that IS the total paid
- Merchant name is usually the first non-numeric line at the very top

OUTPUT SCHEMA:
{{
  "amount": <number or null>,
  "category": "<Category or null>",
  "description": "<summary of purchase or null>",
  "merchant": "<store/restaurant name or null>",
  "date": "<YYYY-MM-DD or null>",
  "items_detected": <number of line items found, or 0>,
  "is_partial_receipt": <true if receipt appears cut off or incomplete>,
  "extraction_notes": "<note about ambiguity, multiple totals, etc. or null>"
}}"""


class ReceiptExtractor:
    """
    Extracts structured expense data from OCR text of receipts.

    Key differences from voice extraction:
    - TOTAL disambiguation: receipts have subtotals, tax, service charge — must pick grand total
    - Layout awareness: uses flagged lines (is_likely_total, is_likely_merchant) as hints
    - Items summarization: converts item lists into a single description
    - Partial receipt handling: returns is_partial_receipt flag back
    - OCR error correction: Gemini handles common OCR mistakes (0 vs O, 1 vs l, etc.)
    """

    MODEL_NAME = "gemini-2.5-flash-lite"

    # Few-shot examples for receipt-specific patterns
    FEW_SHOT_EXAMPLES = """
EXAMPLES:

Input OCR text:
"SUBWAY
123 MG Road, Bangalore
Date: 12/06/2026  Time: 13:45
VEGGIE DELITE 6 INCH    120.00
COOKIE                   40.00
SUBTOTAL                160.00
GST 5%                    8.00
TOTAL                   168.00
CASH PAID               200.00
CHANGE                   32.00
Thank you!"

Output: {"amount": 168.00, "category": "Food", "description": "Subway meal - veggie sub and cookie", "merchant": "Subway", "date": "2026-06-12", "items_detected": 2, "is_partial_receipt": false, "extraction_notes": null}

---

Input OCR text:
"TOTAL         450
GST           22.5
GRAND TOTAL   472.50
VISA ****1234"

Output: {"amount": 472.50, "category": null, "description": "Purchase", "merchant": null, "date": null, "items_detected": 0, "is_partial_receipt": true, "extraction_notes": "Partial receipt - merchant name and date missing. Used GRAND TOTAL of 472.50"}

---

Input OCR text:
"RELIANCE FRESH
GSTIN: 27AABCR1234A1Z5
Milk 1L          62.00
Bread            45.00
Eggs 12pc        89.00
Vegetables       156.00
Sub Total        352.00
Discount         -17.60
Net Amount       334.40
SGST 2.5%         8.36
CGST 2.5%         8.36
Bill Amount      351.12
UPI Payment      351.12
13-06-2026 09:23 AM"

Output: {"amount": 351.12, "category": "Food", "description": "Groceries - milk, bread, eggs, vegetables", "merchant": "Reliance Fresh", "date": "2026-06-13", "items_detected": 4, "is_partial_receipt": false, "extraction_notes": "Used Bill Amount (351.12) as final total including taxes"}

---

Input OCR text:
"HPCL FUEL STATION
Pump No: 4
Product: MS PETROL
Qty: 5.00 L
Rate: 106.31/L
Amount: 531.55
Date: 11/06/2026"

Output: {"amount": 531.55, "category": "Transport", "description": "Petrol 5L at HPCL fuel station", "merchant": "HPCL Fuel Station", "date": "2026-06-11", "items_detected": 1, "is_partial_receipt": false, "extraction_notes": null}"""

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=self.MODEL_NAME,
            generation_config=genai.GenerationConfig(
                temperature=0.0,   # Zero temp for receipts — we want exact extraction
                max_output_tokens=2048,
            ),
        )

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def extract(
        self,
        ocr_text: str,
        flagged_hints: Optional[dict] = None,
        
    ) -> dict:
        """
        Extract structured expense from OCR text.

        Args:
            ocr_text: Raw text from PaddleOCR (preserves top-to-bottom order)
            flagged_hints: Optional dict of {'likely_total_lines': [...], 'likely_merchant': '...'}
                           from PaddleOCR structural analysis

        Returns:
            Dict with amount, category, description, merchant, date, and metadata
        """
        today = date.today()
        system = RECEIPT_SYSTEM_PROMPT.format(today=today.isoformat())

        # Build context-enriched prompt with structural hints
        hint_section = ""
        if flagged_hints:
            hints = []

            if flagged_hints.get("detected_total"):
                hints.append(
                    f"Detected total amount from OCR analysis: "
                    f"{flagged_hints['detected_total']}"
                )

            if flagged_hints.get("likely_total_lines"):
                hints.append(
                    f"Lines likely containing totals: "
                    f"{flagged_hints['likely_total_lines']}"
                )

            if flagged_hints.get("likely_merchant"):
                hints.append(
                    f"Likely merchant (top of receipt): "
                    f"{flagged_hints['likely_merchant']}"
                )

            if flagged_hints.get("likely_date_lines"):
                hints.append(
                    f"Lines likely containing dates: "
                    f"{flagged_hints['likely_date_lines']}"
                )

            if hints:
                hint_section = (
                    "\n\nSTRUCTURAL HINTS from OCR analysis:\n"
                    + "\n".join(hints)
                )

        prompt = (
            f"{system}\n\n"
            f"---\n\n"
            f"Now extract from this OCR text:{hint_section}\n\n"
            f"Input OCR text:\n\"{ocr_text}\"\n\n"
            f"Output:"
        )

        logger.info(
            f"Extracting from receipt OCR ({len(ocr_text)} chars)"
        )
        print("\n===== OCR TEXT SENT TO GEMINI =====")
        print(ocr_text)
        print("===================================")
        response = await self.model.generate_content_async(prompt)
        raw_json = response.text.strip()

        # Remove Gemini markdown fences
        if raw_json.startswith("```"):
            raw_json = raw_json.replace("```json", "")
            raw_json = raw_json.replace("```", "")
            raw_json = raw_json.strip()

        print("\n===== GEMINI RESPONSE =====")
        print(raw_json)
        print("===========================\n")
        print("\n===== FINISH REASON =====")
        print(response.candidates[0].finish_reason)
        print("=========================\n")

        logger.debug(f"Gemini receipt response: {raw_json}")

        return self._parse_and_normalize(raw_json, today)

    def _parse_and_normalize(self, raw_json: str, today: date) -> dict:
        """Parse response and normalize all fields to correct Python types."""
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error(f"Receipt JSON parse error: {e}\nRaw: {raw_json}")
            data = self._recover_from_malformed(raw_json)

        return {
            "amount":              self._parse_amount(data.get("amount")),
            "category":            self._parse_category(data.get("category")),
            "description":         self._clean_string(data.get("description")),
            "merchant":            self._clean_string(data.get("merchant")),
            "date":                self._parse_date(data.get("date"), today),
            "items_detected":      int(data.get("items_detected", 0) or 0),
            "is_partial_receipt":  bool(data.get("is_partial_receipt", False)),
            "extraction_notes":    self._clean_string(data.get("extraction_notes")),
        }

    def _parse_amount(self, value) -> Optional[Decimal]:
        if value is None:
            return None

        try:
            cleaned = str(value).replace(",", "").strip()
            amount = Decimal(cleaned)

            if amount <= 0:
                return None

            return amount

        except (InvalidOperation, ValueError):
            logger.warning(f"Cannot parse receipt amount: {value}")
            return None

    def _parse_category(self, value) -> Optional[ExpenseCategory]:
        if not value:
            return None
        normalized = str(value).strip().title()
        try:
            return ExpenseCategory(normalized)
        except ValueError:
            for cat in ExpenseCategory:
                if cat.value.lower() in normalized.lower():
                    return cat
            return ExpenseCategory.OTHER

    def _parse_date(self, value, today: date) -> Optional[date]:
        if not value:
            return None

        formats = [
            "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
            "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d",
            "%d %b %Y", "%d %B %Y", "%b %d %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(str(value), fmt).date()
            except ValueError:
                continue

        logger.warning(f"Cannot parse receipt date: {value}")
        return None

    def _clean_string(self, value) -> Optional[str]:
        if not value:
            return None
        cleaned = str(value).strip()
        return cleaned if cleaned and cleaned.lower() not in ("null", "none", "") else None

    def _recover_from_malformed(self, text: str) -> dict:
        """Regex fallback when JSON is malformed."""
        import re
        data = {}
        for key in ["amount", "category", "merchant", "date", "description"]:
            match = re.search(rf'"{key}"\s*:\s*"?([^",\}}]+)"?', text)
            if match:
                data[key] = match.group(1).strip().strip('"')
        logger.warning(f"Recovered from malformed JSON: {data}")
        return data
