import io
import logging
from datetime import date

from app.services.export_service import ExportSummary

logger = logging.getLogger(__name__)


def generate_csv(summary: ExportSummary) -> bytes:
    """
    Generate a clean CSV file from export summary.

    Uses pandas for proper escaping of commas, quotes, and
    special characters in descriptions/merchants.

    Returns bytes ready to stream as a file download.
    """
    try:
        import pandas as pd
    except ImportError:
        # Fallback: manual CSV if pandas not available
        return _manual_csv(summary)

    if not summary.rows:
        # Return CSV with just headers if no data
        df = pd.DataFrame(columns=[
            "Date", "Description", "Category", "Amount",
            "Merchant", "Source", "AI Confidence"
        ])
        return df.to_csv(index=False).encode("utf-8-sig")

    # Build rows as dicts — pandas handles all escaping
    data = [
        {
            "Date":          row.date,
            "Description":   row.description,
            "Category":      row.category,
            "Amount (INR)":  row.amount_raw,      # raw number for Excel formulas
            "Amount":        row.amount,           # formatted with ₹ for readability
            "Merchant":      row.merchant,
            "Source":        row.source,
            "AI Confidence": row.confidence,
        }
        for row in summary.rows
    ]

    df = pd.DataFrame(data)

    # Add a summary section at the bottom
    # (blank row + summary stats — readable in Excel)
    summary_rows = pd.DataFrame([
        {},
        {"Date": "── SUMMARY ──"},
        {"Date": "Export Date",      "Description": summary.export_date},
        {"Date": "Period",           "Description": summary.date_range_label},
        {"Date": "Total Expenses",   "Description": summary.total_amount},
        {"Date": "Total Count",      "Description": str(summary.total_count)},
        {"Date": "Average per Item", "Description": summary.average_amount},
        {"Date": "Top Category",     "Description": summary.top_category},
        {},
        {"Date": "── CATEGORY BREAKDOWN ──"},
    ])

    for cat in summary.category_breakdown:
        summary_rows = pd.concat([
            summary_rows,
            pd.DataFrame([{
                "Date":        cat["category"],
                "Description": cat["total_fmt"],
                "Category":    f"{cat['percentage']}%",
                "Amount":      f"{cat['count']} transactions",
            }])
        ], ignore_index=True)

    # utf-8-sig adds BOM — makes Excel open ₹ symbol correctly
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.write("\n")
    summary_rows.to_csv(output, index=False, header=False)

    return output.getvalue().encode("utf-8-sig")


def _manual_csv(summary: ExportSummary) -> bytes:
    """Fallback CSV generator without pandas."""
    lines = ["Date,Description,Category,Amount,Merchant,Source,AI Confidence"]
    for row in summary.rows:
        # Escape fields that might contain commas
        desc = f'"{row.description}"' if "," in row.description else row.description
        merch = f'"{row.merchant}"' if "," in row.merchant else row.merchant
        lines.append(
            f"{row.date},{desc},{row.category},{row.amount_raw},"
            f"{merch},{row.source},{row.confidence}"
        )
    return "\n".join(lines).encode("utf-8-sig")
