from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from app.ai.assistant.intent_classifier import TimePeriod


@dataclass
class DateRange:
    start: date
    end: date
    label: str   # human-readable label for response generation

    def __str__(self) -> str:
        return self.label


class DateResolver:
    """
    Converts a TimePeriod enum into a concrete (start, end) date range.

    Why Python, not SQL?
    - DB-agnostic: no DATE_TRUNC, no DATEADD dialects
    - Testable: pure functions, no DB dependency
    - Consistent: "this month" means the same thing everywhere
    - Predictable: date logic is visible and auditable
    """

    def resolve(self, period: TimePeriod, reference: date | None = None) -> DateRange:
        today = reference or date.today()

        match period:
            case TimePeriod.TODAY:
                return DateRange(today, today, "today")

            case TimePeriod.THIS_WEEK:
                start = today - timedelta(days=today.weekday())  # Monday
                return DateRange(start, today, "this week")

            case TimePeriod.THIS_MONTH:
                start = today.replace(day=1)
                return DateRange(start, today, "this month")

            case TimePeriod.LAST_MONTH:
                first_this_month = today.replace(day=1)
                last_day_last = first_this_month - timedelta(days=1)
                start = last_day_last.replace(day=1)
                return DateRange(start, last_day_last, "last month")

            case TimePeriod.LAST_7_DAYS:
                start = today - timedelta(days=6)
                return DateRange(start, today, "the last 7 days")

            case TimePeriod.LAST_30_DAYS:
                start = today - timedelta(days=29)
                return DateRange(start, today, "the last 30 days")

            case TimePeriod.LAST_3_MONTHS:
                # Go back 3 months from first of current month
                month = today.month - 3
                year = today.year
                if month <= 0:
                    month += 12
                    year -= 1
                start = date(year, month, 1)
                return DateRange(start, today, "the last 3 months")

            case TimePeriod.THIS_YEAR:
                start = today.replace(month=1, day=1)
                return DateRange(start, today, f"this year ({today.year})")

            case TimePeriod.ALL_TIME:
                # Use a far-past date as lower bound
                return DateRange(date(2000, 1, 1), today, "all time")

            case _:
                # Safe default
                start = today.replace(day=1)
                return DateRange(start, today, "this month")

    def resolve_comparison_periods(
        self, period: TimePeriod, reference: date | None = None
    ) -> tuple[DateRange, DateRange]:
        """
        For trend queries: returns (current_period, previous_period).
        Used by SPENDING_TREND intent.
        """
        today = reference or date.today()
        current = self.resolve(period, today)

        # Calculate equivalent previous period
        duration = (current.end - current.start).days + 1
        prev_end = current.start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=duration - 1)

        previous = DateRange(prev_start, prev_end, f"the previous {duration} days")
        return current, previous
