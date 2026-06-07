import re
from datetime import date
from decimal import Decimal

from app.models.expense import ExpenseCategory


class LocalExtractor:

    def extract(self, text: str) -> dict:
        text_lower = text.lower()

        amount = self._extract_amount(text_lower)
        category = self._extract_category(text_lower)

        print("\n========== LOCAL EXTRACTOR ==========")
        print("TEXT:", text_lower)
        print("AMOUNT:", amount)
        print("CATEGORY:", category)
        print("=====================================\n")

        return {
            "amount": amount,
            "category": category,
            "description": self._extract_description(text),
            "merchant": None,
            "date": date.today(),
            "extraction_notes": "Local extraction",
        }

    def _extract_amount(self, text: str):
        text = text.lower()

        lakh_match = re.search(
            r'(\d+(?:\.\d+)?)\s*lakh',
            text
        )

        if lakh_match:
            return Decimal(lakh_match.group(1)) * Decimal("100000")

        crore_match = re.search(
            r'(\d+(?:\.\d+)?)\s*crore',
            text
        )

        if crore_match:
            return Decimal(crore_match.group(1)) * Decimal("10000000")

        thousand_match = re.search(
            r'(\d+(?:\.\d+)?)\s*thousand',
            text
        )

        if thousand_match:
            return Decimal(thousand_match.group(1)) * Decimal("1000")

        normal_match = re.search(
            r'(\d+(?:\.\d+)?)',
            text
        )

        if normal_match:
            return Decimal(normal_match.group(1))

        return None

    def _extract_category(self, text: str):
        edu_words=[
            "course",
            "tuition",
            "books",
            "school fee",
            "university",
            "college fee",
            "education",
        ]
        shop_words=[
            "mall",
            "store",
            "shop",
            "ecommerce",
            "amazon",
            "flipkart",
        ]


        food_words = [
            "food",
            "lunch",
            "breakfast",
            "dinner",
            "canteen",
            "restaurant",
            "coffee",
            "tea",
            "groceries",
        ]

        transport_words = [
            "uber",
            "auto",
            "taxi",
            "bus",
            "metro",
            "train",
            "fuel",
            "petrol",
        ]

        entertainment_words = [
            "movie",
            "netflix",
            "spotify",
            "game",
        ]

        health_words = [
            "doctor",
            "hospital",
            "medicine",
            "pharmacy",
        ]

        if any(word in text for word in edu_words):
            return ExpenseCategory.EDUCATION

        if any(word in text for word in shop_words):
            return ExpenseCategory.SHOPPING

        if any(word in text for word in food_words):
            return ExpenseCategory.FOOD

        if any(word in text for word in transport_words):
            return ExpenseCategory.TRANSPORT

        if any(word in text for word in entertainment_words):
            return ExpenseCategory.ENTERTAINMENT

        if any(word in text for word in health_words):
            return ExpenseCategory.HEALTH

        return ExpenseCategory.OTHER

    def _extract_description(self, text: str):
        return text.strip()