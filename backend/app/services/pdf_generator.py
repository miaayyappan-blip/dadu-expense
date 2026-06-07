import io
import logging
from datetime import date

from app.services.export_service import ExportSummary

logger = logging.getLogger(__name__)

# ── ReportLab color palette ───────────────────────────────────────────────────
# These match the frontend's green brand color
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    pdfmetrics.registerFont(
        TTFont("Arial", r"C:\Windows\Fonts\arial.ttf")
    )

    pdfmetrics.registerFont(
        TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf")
    )

    registerFontFamily(
        "Arial",
        normal="Arial",
        bold="Arial-Bold"
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not installed — PDF export will be unavailable")


# Brand colors
GREEN       = colors.HexColor("#16a34a")
GREEN_LIGHT = colors.HexColor("#dcfce7")
SLATE_800   = colors.HexColor("#1e293b")
SLATE_500   = colors.HexColor("#64748b")
SLATE_100   = colors.HexColor("#f1f5f9")
SLATE_200   = colors.HexColor("#e2e8f0")
WHITE       = colors.white

# Source badge colors
SOURCE_COLORS = {
    "VOICE":  colors.HexColor("#ede9fe"),   # violet
    "OCR":    colors.HexColor("#dbeafe"),   # blue
    "MANUAL": colors.HexColor("#f1f5f9"),   # slate
}
SOURCE_TEXT_COLORS = {
    "VOICE":  colors.HexColor("#6d28d9"),
    "OCR":    colors.HexColor("#1d4ed8"),
    "MANUAL": colors.HexColor("#475569"),
}


def generate_pdf(summary: ExportSummary) -> bytes:
    """
    Generate a professional PDF expense report.

    Structure:
    1. Header — app name, user, export date, period
    2. Summary stats — 4 key metrics in a grid
    3. Category breakdown table
    4. Full expense list (paginated automatically by ReportLab)
    5. Footer with page numbers on every page
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab is not installed. Run: pip install reportlab")
        try:
            pdfmetrics.registerFont(
                TTFont(
                    "Arial",
                    r"C:\Windows\Fonts\Arial.ttf"
                )
            )
            pdfmetrics.registerFont(
                TTFont(
                    "Arial-Bold",
                    r"C:\Windows\Fonts\Arial-Bold.ttf"
                )
            )
        except:
            pass

    buffer = io.BytesIO()
    PAGE_W, PAGE_H = A4
    MARGIN = 20 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN + 10 * mm,  # extra space for footer
        title=f"Expense Report — {summary.user_name}",
    )

    styles = _build_styles()
    story = []

    # ── 1. Header ─────────────────────────────────────────────────────────────
    story += _build_header(summary, styles, PAGE_W, MARGIN)

    # ── 2. Summary cards ──────────────────────────────────────────────────────
    story += _build_summary_cards(summary, styles, PAGE_W, MARGIN)
    story.append(Spacer(1, 6 * mm))

    # ── 3. Category breakdown ─────────────────────────────────────────────────
    if summary.category_breakdown:
        story.append(Paragraph("Spending by Category", styles["section_title"]))
        story.append(Spacer(1, 3 * mm))
        story += _build_category_table(summary, styles, PAGE_W, MARGIN)
        story.append(Spacer(1, 6 * mm))

    # ── 4. Expense list ───────────────────────────────────────────────────────
    story.append(Paragraph(
        f"All Expenses ({summary.total_count} transactions)",
        styles["section_title"]
    ))
    story.append(Spacer(1, 3 * mm))

    if summary.rows:
        story += _build_expense_table(summary, styles, PAGE_W, MARGIN)
    else:
        story.append(Paragraph("No expenses in this period.", styles["body"]))

    # ── Build PDF ─────────────────────────────────────────────────────────────
    doc.build(
        story,
        onFirstPage=_make_footer(summary),
        onLaterPages=_make_footer(summary),
    )

    return buffer.getvalue()


# ── Builder helpers ───────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()
    styles = {}

    styles["title"] = ParagraphStyle(
        "title",
        fontSize=22, fontName="Arial-Bold",
        textColor=SLATE_800, spaceAfter=2,
    )
    styles["subtitle"] = ParagraphStyle(
        "subtitle",
        fontSize=10, fontName="Arial",
        textColor=SLATE_500, spaceAfter=4,
    )
    styles["section_title"] = ParagraphStyle(
        "section_title",
        fontSize=11, fontName="Arial-Bold",
        textColor=SLATE_800, spaceBefore=4, spaceAfter=2,
    )
    styles["body"] = ParagraphStyle(
        "body",
        fontSize=9, fontName="Arial",
        textColor=SLATE_800,
    )
    styles["muted"] = ParagraphStyle(
        "muted",
        fontSize=8, fontName="Arial",
        textColor=SLATE_500,
    )
    styles["metric_value"] = ParagraphStyle(
        "metric_value",
        fontSize=16, fontName="Arial-Bold",
        textColor=SLATE_800, alignment=TA_CENTER,
    )
    styles["metric_label"] = ParagraphStyle(
        "metric_label",
        fontSize=8, fontName="Arial",
        textColor=SLATE_500, alignment=TA_CENTER,
    )
    return styles


def _build_header(summary, styles, page_w, margin) -> list:
    content_w = page_w - 2 * margin

    # Green accent bar
    bar = Table(
        [[""]],
        colWidths=[content_w],
        rowHeights=[3],
    )
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN),
        ("LINEBELOW", (0, 0), (-1, -1), 0, WHITE),
    ]))

    return [
        bar,
        Spacer(1, 4 * mm),
        Paragraph("Dadu Expense", styles["title"]),
        Spacer(1, 4 * mm),
        Paragraph("Expense Report", styles["subtitle"]),
        Paragraph(
            f"<b>{summary.user_name}</b> &nbsp;·&nbsp; "
            f"Period: {summary.date_range_label} &nbsp;·&nbsp; "
            f"Generated: {summary.export_date}",
            styles["muted"],
        ),
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", thickness=1, color=SLATE_200),
        Spacer(1, 4 * mm),
    ]


def _build_summary_cards(summary, styles, page_w, margin) -> list:
    content_w = page_w - 2 * margin
    col_w = content_w / 4 - 2 * mm

    metrics = [
        (summary.total_amount,    "Total Spent"),
        (str(summary.total_count), "Transactions"),
        (summary.average_amount,  "Avg per Expense"),
        (summary.top_category,    "Top Category"),
    ]

    cells = []
    for value, label in metrics:
        cell_table = Table(
            [[Paragraph(value, styles["metric_value"])],
             [Paragraph(label, styles["metric_label"])]],
            colWidths=[col_w],
        )
        cell_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), SLATE_100),
            ("ROUNDEDCORNERS", [4]),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        cells.append(cell_table)

    row_table = Table(
        [cells],
        colWidths=[col_w + 2 * mm] * 4,
    )
    row_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))

    return [row_table]


def _build_category_table(summary, styles, page_w, margin) -> list:
    content_w = page_w - 2 * margin

    # Header row
    headers = ["Category", "Transactions", "Total Spent", "% of Total", "Visual"]
    col_widths = [content_w * 0.22, content_w * 0.15,
                  content_w * 0.20, content_w * 0.13, content_w * 0.30]

    rows = [headers]
    for cat in summary.category_breakdown[:8]:  # max 8 categories
        # Simple bar made of filled blocks
        bar_width = int(cat["percentage"] / 100 * 20)
        bar = "█" * bar_width + "░" * (20 - bar_width)

        rows.append([
            cat["category"],
            str(cat["count"]),
            cat["total_fmt"],
            f"{cat['percentage']}%",
            bar,
        ])

    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        # Header
        ("BACKGROUND",   (0, 0), (-1, 0),  GREEN),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Arial-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  9),
        ("BOTTOMPADDING",(0, 0), (-1, 0),  6),
        ("TOPPADDING",   (0, 0), (-1, 0),  6),
        # Data rows
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("FONTNAME",     (0, 1), (-1, -1), "Arial"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, SLATE_100]),
        ("TOPPADDING",   (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 4),
        ("TEXTCOLOR",    (4, 1), (4, -1),  GREEN),  # bar column green
        # Grid
        ("LINEBELOW",    (0, 0), (-1, -1), 0.5, SLATE_200),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN",        (1, 0), (3, -1),  "RIGHT"),
    ]))

    return [t]


def _build_expense_table(summary, styles, page_w, margin) -> list:
    content_w = page_w - 2 * margin

    headers = [
    "Date",
    "Description",
    "Category",
    "Amount",
    "Merchant",
    "Source",
    "Confidence"
]
    col_widths = [
    content_w * 0.09,
    content_w * 0.31,
    content_w * 0.11,
    content_w * 0.11,
    content_w * 0.16,
    content_w * 0.10,
    content_w * 0.12,
]

    rows = [headers]
    for row in summary.rows:
        rows.append([
            row.date,
            row.description[:45] + "…" if len(row.description) > 45 else row.description,
            row.category,
            row.amount,
            row.merchant[:25] + "…" if len(row.merchant) > 25 else row.merchant,
            row.source,
            row.confidence
        ])

    t = Table(rows, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0),  GREEN),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Arial-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  9),
        ("TOPPADDING",    (0, 0), (-1, 0),  6),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  6),
        # Data rows
        ("FONTSIZE",      (0, 1), (-1, -1), 7.5),
        ("FONTNAME",      (0, 1), (-1, -1), "Arial"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, SLATE_100]),
        ("TOPPADDING",    (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        # Grid
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, SLATE_200),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        # Amount right-aligned
        ("ALIGN",         (3, 0), (3, -1),  "RIGHT"),
        ("FONTNAME",      (3, 1), (3, -1),  "Arial-Bold"),
    ]

    # Color-code source column per row
    for i, row in enumerate(summary.rows, start=1):
        src = row.source
        bg = SOURCE_COLORS.get(src, SLATE_100)
        tc = SOURCE_TEXT_COLORS.get(src, SLATE_500)
        style_cmds += [
            ("BACKGROUND", (5, i), (5, i), bg),
            ("TEXTCOLOR",  (5, i), (5, i), tc),
            ("FONTNAME",   (5, i), (5, i), "Arial-Bold"),
        ]

    t.setStyle(TableStyle(style_cmds))
    return [t]


def _make_footer(summary):
    """Returns a footer function called by ReportLab on every page."""
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Arial", 7)
        canvas.setFillColor(SLATE_500)

        # Left: app name
        canvas.drawString(
            doc.leftMargin,
            doc.bottomMargin - 5 * mm,
            f"Dadu Expense — {summary.user_name}",
        )

        # Right: page number
        page_text = f"Page {doc.page}"
        canvas.drawRightString(
            doc.width + doc.leftMargin,
            doc.bottomMargin - 5 * mm,
            page_text,
        )

        # Center: generation date
        canvas.drawCentredString(
            doc.width / 2 + doc.leftMargin,
            doc.bottomMargin - 5 * mm,
            f"Generated {summary.export_date}",
        )

        canvas.restoreState()

    return footer
