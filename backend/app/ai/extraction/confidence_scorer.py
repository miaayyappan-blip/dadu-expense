from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from app.models.expense import ExpenseCategory


@dataclass
class ConfidenceBreakdown:
    """
    Transparent breakdown of how confidence was computed.
    Returned to the frontend so the UI can show specific warnings.
    """
    score: float                        # Final 0.0–1.0 score
    missing_fields: list[str]           # Fields not found
    low_confidence_fields: list[str]    # Fields found but uncertain
    suggestions: str                    # Human-readable explanation
    field_scores: dict[str, float]      # Per-field score contribution


class ConfidenceScorer:
    """
    Computes a deterministic confidence score for an AI-extracted expense.

    Scoring weights (must sum to 1.0):
        amount      0.35  — most critical field, can't save without it
        category    0.25  — important for analytics
        date        0.25  — important for timeline accuracy
        description 0.10  — useful but can be inferred
        merchant    0.05  — nice-to-have

    Thresholds:
        >= 0.85  → Auto-accept safe (show confirmation, no warning)
        0.60–0.84 → Show review UI with yellow warning
        < 0.60   → Show review UI with red warning, highlight missing fields
    """

    WEIGHTS = {
        "amount":      0.35,
        "category":    0.25,
        "date":        0.25,
        "description": 0.10,
        "merchant":    0.05,
    }

    # Categories that LLMs often confuse — lower their score
    AMBIGUOUS_CATEGORIES = {ExpenseCategory.OTHER}

    def score(
        self,
        amount: Optional[Decimal],
        category: Optional[ExpenseCategory],
        description: Optional[str],
        merchant: Optional[str],
        expense_date: Optional[date],
        raw_text: str,
    ) -> ConfidenceBreakdown:
        field_scores: dict[str, float] = {}
        missing_fields: list[str] = []
        low_confidence_fields: list[str] = []
        issues: list[str] = []

        # ── Amount ────────────────────────────────────────────────────────────
        amount_score = self._score_amount(amount, raw_text)
        field_scores["amount"] = amount_score
        if amount is None:
            missing_fields.append("amount")
            issues.append("Could not find a monetary amount")
        elif amount_score < 0.7:
            low_confidence_fields.append("amount")
            issues.append(f"Amount {amount} may be incorrect — please verify")

        # ── Category ──────────────────────────────────────────────────────────
        category_score = self._score_category(category, raw_text)
        field_scores["category"] = category_score
        if category is None:
            missing_fields.append("category")
            issues.append("Could not determine expense category")
        elif category in self.AMBIGUOUS_CATEGORIES:
            low_confidence_fields.append("category")
            issues.append("Category was set to 'Other' — you may want to update it")

        # ── Date ──────────────────────────────────────────────────────────────
        date_score = self._score_date(expense_date, raw_text)
        field_scores["date"] = date_score
        if expense_date is None:
            missing_fields.append("date")
            issues.append("No date mentioned — defaulted to today")
        elif date_score < 0.7:
            low_confidence_fields.append("date")
            issues.append(f"Date {expense_date} may be incorrect — please verify")

        # ── Description ───────────────────────────────────────────────────────
        desc_score = self._score_description(description, raw_text)
        field_scores["description"] = desc_score
        if not description:
            missing_fields.append("description")

        # ── Merchant ─────────────────────────────────────────────────────────
        merchant_score = 1.0 if merchant else 0.0
        field_scores["merchant"] = merchant_score
        # Merchant is optional — not added to missing_fields

        # ── Weighted final score ───────────────────────────────────────────────
        final_score = sum(
            self.WEIGHTS[field] * field_scores.get(field, 0.0)
            for field in self.WEIGHTS
        )
        final_score = round(min(1.0, max(0.0, final_score)), 3)

        # ── Build human-readable suggestion ───────────────────────────────────
        if final_score >= 0.85:
            suggestion = "Expense extracted successfully. Please review and confirm."
        elif final_score >= 0.60:
            if issues:
                suggestion = f"Some fields need attention: {'; '.join(issues)}"
            else:
                suggestion = "Please review the extracted expense before saving."
        else:
            suggestion = (
                f"Low confidence extraction. Please fill in missing details. "
                f"Issues: {'; '.join(issues) if issues else 'Multiple fields unclear'}"
            )

        return ConfidenceBreakdown(
            score=final_score,
            missing_fields=missing_fields,
            low_confidence_fields=low_confidence_fields,
            suggestions=suggestion,
            field_scores=field_scores,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _score_amount(self, amount: Optional[Decimal], raw_text: str) -> float:
        if amount is None:
            return 0.0

        score = 1.0

        # Unrealistically large amounts are suspicious
        if amount > Decimal("1000000"):
            score *= 0.3
        elif amount > Decimal("100000"):
            score *= 0.6

        # Amounts with no decimal part are slightly less certain
        # (e.g. "fifty rupees" → 50 is fine, but "five" → 5 might be 50)
        if amount == amount.quantize(Decimal("1")) and amount < 10:
            score *= 0.7

        # Check if a numeric string for this amount appears in the raw text
        # If yes, high confidence. If extracted purely by inference, lower.
        amount_str = str(int(amount)) if amount == int(amount) else str(amount)
        if amount_str in raw_text.replace(",", "").replace(" ", ""):
            score = min(1.0, score * 1.1)  # slight boost for verbatim match

        return round(score, 3)

    def _score_category(
        self, category: Optional[ExpenseCategory], raw_text: str
    ) -> float:
        if category is None:
            return 0.0
        if category == ExpenseCategory.OTHER:
            return 0.5  # penalize catch-all
        return 1.0

    def _score_date(self, expense_date: Optional[date], raw_text: str) -> float:
        if expense_date is None:
            return 0.0

        today = date.today()
        score = 1.0

        # Future dates are suspicious for expenses
        if expense_date > today:
            score *= 0.2

        # Very old dates are also suspicious (likely parsing error)
        days_old = (today - expense_date).days
        if days_old > 365:
            score *= 0.4
        elif days_old > 90:
            score *= 0.7

        # If today's date was used (default fallback), lower confidence
        if expense_date == today:
            # Check if there was any date-like text in the transcript
            date_keywords = [
                "today", "yesterday", "last", "monday", "tuesday", "wednesday",
                "thursday", "friday", "saturday", "sunday", "january", "february",
                "march", "april", "may", "june", "july", "august", "september",
                "october", "november", "december",
            ]
            has_date_mention = any(
                kw in raw_text.lower() for kw in date_keywords
            )
            # Digit patterns like "5th", "12/06" etc
            import re
            has_date_digit = bool(re.search(r"\d{1,2}[/\-]\d{1,2}", raw_text))

            if not has_date_mention and not has_date_digit:
                score *= 0.6  # defaulted to today with no date in transcript

        return round(score, 3)

    def _score_description(
        self, description: Optional[str], raw_text: str
    ) -> float:
        if not description:
            return 0.0
        if len(description) < 5:
            return 0.5
        return 1.0
