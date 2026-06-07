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

# ── System prompt ──────────────────────────────────────────────────────────────
# Engineered for:
# 1. Consistent JSON output (no markdown, no preamble)
# 2. Explicit null for missing fields (never guess)
# 3. Category mapping to our enum values
# 4. Date normalization to ISO format
EXTRACTION_SYSTEM_PROMPT = """You are an expense extraction engine. Extract structured expense data from user input.

RULES:
1. Return ONLY valid JSON. No markdown, no explanation, no preamble.
2. If a field cannot be determined with reasonable confidence, return null for that field.
3. Never invent data. Only extract what is explicitly or very clearly implied.
4. Amounts must be numeric only (no currency symbols).
5. Dates must be ISO format: YYYY-MM-DD. If year is not mentioned, use current year.
6. "yesterday" = subtract 1 day from today. "last monday" = calculate the actual date.
7. Today's date for reference: {today}

CATEGORIES (use exactly these values):
- Food (meals, restaurants, groceries, snacks, beverages, canteen, cafe)
- Transport (uber, auto, bus, train, metro, taxi, fuel, parking, flight)
- Shopping (clothes, electronics, household items, online shopping, amazon, flipkart)
- Entertainment (movies, games, events, concerts, subscriptions, netflix, spotify)
- Health (medicine, doctor, hospital, gym, pharmacy, medical)
- Utilities (electricity, water, internet, phone bill, gas, rent)
- Education (books, courses, tuition, school fees, stationery)
- Travel (hotels, resorts, holiday, trip, vacation)
- Other (anything that doesn't fit above)

OUTPUT SCHEMA:
{{
  "amount": <number or null>,
  "category": "<Category from list above or null>",
  "description": "<brief description of the expense or null>",
  "merchant": "<merchant/vendor name or null>",
  "date": "<YYYY-MM-DD or null>",
  "extraction_notes": "<brief note about ambiguity or missing info, or null>"
}}"""


class GeminiExtractor:
    """
    Uses Gemini Flash for fast, cost-effective structured extraction.
    
    Design decisions:
    - gemini-1.5-flash: faster and cheaper than Pro, sufficient for extraction
    - response_mime_type="application/json": forces JSON output without parsing markdown
    - Temperature 0.1: near-deterministic but allows slight flexibility for date math
    - Two-shot examples in the prompt improve accuracy on edge cases
    """

    MODEL_NAME = "gemini-2.0-flash"

    # Few-shot examples appended to each prompt — significantly improves accuracy
    FEW_SHOT_EXAMPLES = """
EXAMPLES:

Input: "spent 250 bucks on lunch at canteen today"
Output: {{"amount": 250, "category": "Food", "description": "Lunch at canteen", "merchant": "Canteen", "date": "{today}", "extraction_notes": null}}

Input: "uber to airport yesterday 680"
Output: {{"amount": 680, "category": "Transport", "description": "Uber ride to airport", "merchant": "Uber", "date": "{yesterday}", "extraction_notes": null}}

Input: "bought something expensive"
Output: {{"amount": null, "category": "Shopping", "description": "Purchase", "merchant": null, "date": null, "extraction_notes": "Amount not specified. Category assumed Shopping but may be Other."}}

Input: "Netflix subscription 649"
Output: {{"amount": 649, "category": "Entertainment", "description": "Netflix subscription", "merchant": "Netflix", "date": null, "extraction_notes": "Date not mentioned"}}

Input: "paid five hundred for medicine at Apollo"
Output: {{"amount": 500, "category": "Health", "description": "Medicine", "merchant": "Apollo Pharmacy", "date": null, "extraction_notes": null}}

Input: "groceries 1200 last saturday"
Output: {{"amount": 1200, "category": "Food", "description": "Groceries", "merchant": null, "date": "{last_saturday}", "extraction_notes": null}}
"""

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=self.MODEL_NAME,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=512,
            ),
        )

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def extract(self, text: str) -> dict:
        """
        Extract structured expense fields from free-form text.
        
        Args:
            text: Transcribed speech or raw OCR text
            
        Returns:
            Dict with amount, category, description, merchant, date, extraction_notes
            All fields may be None if not found.
        """
        today = date.today()
        from datetime import timedelta
        yesterday = today - timedelta(days=1)
        # Compute last saturday
        days_since_saturday = (today.weekday() - 5) % 7
        last_saturday = today - timedelta(days=days_since_saturday or 7)

        system = EXTRACTION_SYSTEM_PROMPT.format(today=today.isoformat())
        examples = self.FEW_SHOT_EXAMPLES.format(
            today=today.isoformat(),
            yesterday=yesterday.isoformat(),
            last_saturday=last_saturday.isoformat(),
        )

        prompt = f"{system}\n\n{examples}\n\nNow extract from this input:\nInput: \"{text}\"\nOutput:"

        logger.info(f"Extracting expense from: '{text[:100]}{'...' if len(text) > 100 else ''}'")

        response = await self.model.generate_content_async(prompt)
        raw_json = response.text.strip()

        logger.debug(f"Gemini raw response: {raw_json}")

        return self._parse_and_normalize(raw_json, today)

    def _parse_and_normalize(self, raw_json: str, today: date) -> dict:
        """
        Parse Gemini's JSON response and normalize all field types.
        Never raises — returns partial data on parse errors.
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON: {e}\nRaw: {raw_json}")
            # Attempt to extract from malformed response
            data = self._recover_from_malformed(raw_json)

        return {
            "amount":           self._parse_amount(data.get("amount")),
            "category":         self._parse_category(data.get("category")),
            "description":      self._clean_string(data.get("description")),
            "merchant":         self._clean_string(data.get("merchant")),
            "date":             self._parse_date(data.get("date"), today),
            "extraction_notes": self._clean_string(data.get("extraction_notes")),
        }

    def _parse_amount(self, value) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
            return amount if amount > 0 else None
        except (InvalidOperation, ValueError):
            logger.warning(f"Could not parse amount: {value}")
            return None

    def _parse_category(self, value) -> Optional[ExpenseCategory]:
        if not value:
            return None
        # Normalize: strip whitespace, title case
        normalized = str(value).strip().title()
        try:
            return ExpenseCategory(normalized)
        except ValueError:
            # Fuzzy fallback — try partial match
            for cat in ExpenseCategory:
                if cat.value.lower() in normalized.lower():
                    return cat
            logger.warning(f"Unknown category: {value}, defaulting to Other")
            return ExpenseCategory.OTHER

    def _parse_date(self, value, today: date) -> Optional[date]:
        if not value:
            return None
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            logger.warning(f"Could not parse date: {value}")
            return None

    def _clean_string(self, value) -> Optional[str]:
        if not value:
            return None
        cleaned = str(value).strip()
        return cleaned if cleaned and cleaned.lower() not in ("null", "none", "") else None

    def _recover_from_malformed(self, text: str) -> dict:
        """Last-resort extraction using regex when JSON parsing fails."""
        import re
        data = {}

        # Try to find amount
        amount_match = re.search(r'"amount"\s*:\s*(\d+(?:\.\d+)?)', text)
        if amount_match:
            data["amount"] = float(amount_match.group(1))

        # Try to find category
        cat_match = re.search(r'"category"\s*:\s*"([^"]+)"', text)
        if cat_match:
            data["category"] = cat_match.group(1)

        logger.warning(f"Recovered partial data from malformed JSON: {data}")
        return data
