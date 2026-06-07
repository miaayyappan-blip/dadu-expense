# Import all models here so SQLAlchemy's metadata is aware of them.
# Alembic reads Base.metadata — all models must be imported before autogenerate works.
from app.models.user import User
from app.models.expense import Expense, ExpenseCategory, ExpenseSource
from app.models.budget import Budget, RecurringExpense, RecurrenceInterval

__all__ = [
    "User",
    "Expense",
    "ExpenseCategory",
    "ExpenseSource",
    "Budget",
    "RecurringExpense",
    "RecurrenceInterval",
]
