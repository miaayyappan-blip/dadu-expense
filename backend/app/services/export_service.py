from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.budget import Budget


@dataclass
class ExportRow:
    """Single expense row ready for export — all fields pre-formatted as strings."""
    date: str
    description: str
    category: str
    amount: str           # formatted: "₹1,234.00"
    amount_raw: float     # raw float for PDF calculations
    merchant: str
    source: str
    confidence: str       # "94%" or "—"


@dataclass
class ExportSummary:
    """Aggregate stats included in PDF header."""
    user_name: str
    export_date: str
    date_range_label: str
    total_amount: str
    total_count: int
    average_amount: str
    top_category: str
    category_breakdown: list[dict]   # [{category, total, count, percentage}]
    rows: list[ExportRow]


class ExportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_export_data(
        self,
        user_id: int,
        user_name: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> ExportSummary:
        """
        Fetch all expenses for a user, formatted for export.
        Returns both raw rows and aggregate summary stats.
        """
        conditions = [Expense.user_id == user_id]
        if date_from:
            conditions.append(Expense.date >= date_from)
        if date_to:
            conditions.append(Expense.date <= date_to)

        # ── Fetch all expenses ────────────────────────────────────────────────
        result = await self.db.execute(
            select(Expense)
            .where(and_(*conditions))
            .order_by(desc(Expense.date), desc(Expense.created_at))
        )
        expenses = list(result.scalars().all())

        # ── Build export rows ─────────────────────────────────────────────────
        rows = [
            ExportRow(
                date=str(e.date),
                description=e.description,
                category=e.category.value,
                amount=f"₹{e.amount:,.2f}",
                amount_raw=float(e.amount),
                merchant=e.merchant or "—",
                source=e.source.value,
                confidence=f"{int(e.confidence * 100)}%" if e.confidence else "—",
            )
            for e in expenses
        ]

        # ── Aggregate stats ───────────────────────────────────────────────────
        total_raw = sum(r.amount_raw for r in rows)
        avg_raw = total_raw / len(rows) if rows else 0.0

        # Category breakdown
        cat_map: dict[str, dict] = {}
        for e in expenses:
            cat = e.category.value
            if cat not in cat_map:
                cat_map[cat] = {"category": cat, "total": 0.0, "count": 0}
            cat_map[cat]["total"] += float(e.amount)
            cat_map[cat]["count"] += 1

        # Sort by total descending, add percentage
        breakdown = sorted(cat_map.values(), key=lambda x: x["total"], reverse=True)
        for item in breakdown:
            item["percentage"] = round(item["total"] / total_raw * 100, 1) if total_raw > 0 else 0.0
            item["total_fmt"] = f"₹{item['total']:,.2f}"

        top_category = breakdown[0]["category"] if breakdown else "—"

        # Date range label
        if date_from and date_to:
            range_label = f"{date_from} to {date_to}"
        elif date_from:
            range_label = f"From {date_from}"
        else:
            range_label = "All time"

        return ExportSummary(
            user_name=user_name,
            export_date=str(date.today()),
            date_range_label=range_label,
            total_amount=f"₹{total_raw:,.2f}",
            total_count=len(rows),
            average_amount=f"₹{avg_raw:,.2f}",
            top_category=top_category,
            category_breakdown=breakdown,
            rows=rows,
        )
