import json
import logging

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.assistant.intent_classifier import QueryIntent
from app.ai.assistant.query_engine import QueryResult
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Response generation prompt ────────────────────────────────────────────────
# The LLM receives REAL DATA and formats it — it does NOT compute or guess.
# Critical rules prevent hallucination of financial figures.
RESPONSE_PROMPT = """You are a helpful personal expense assistant. Write a clear, friendly answer
to a user's expense question based ONLY on the real data provided below.

RULES:
1. Use ONLY the numbers in the DATA section — never invent or estimate figures
2. Format currency as ₹X,XXX (Indian rupees with commas)
3. Be conversational and helpful, 1-3 sentences maximum
4. If no data found, say so clearly and suggest they add expenses
5. Don't repeat the question — just answer it
6. Mention specific insights when the data supports it (e.g., "that's up 20%")
7. Never say you "queried a database" — just answer naturally

USER'S QUESTION: {query}

INTENT TYPE: {intent}

DATA:
{data}

Write your answer (plain text, no markdown):"""

# ── Fallback templates (when Gemini is unavailable) ───────────────────────────
# These provide reasonable answers from pure data without any LLM call.
FALLBACK_TEMPLATES: dict[QueryIntent, str] = {
    QueryIntent.TOTAL_SPEND_PERIOD:
        "You spent ₹{total:,.0f} across {count} transactions {period}.",

    QueryIntent.CATEGORY_SPEND_PERIOD:
        "You spent ₹{total:,.0f} on {category} {period} across {count} transactions.",

    QueryIntent.TOP_EXPENSES:
        "Your top expense {period} was ₹{top_amount:,.0f} — {top_desc}.",

    QueryIntent.SPENDING_TREND:
        "You spent ₹{current_total:,.0f} {current_period} vs ₹{previous_total:,.0f} "
        "{previous_period} — a {change_word} of {abs_change:.0f}%.",

    QueryIntent.CATEGORY_COMPARISON:
        "Comparing spending {period}: {summary}",

    QueryIntent.MERCHANT_SPEND:
        "You spent ₹{total:,.0f} at {merchant_query} {period}.",

    QueryIntent.RECENT_EXPENSES:
        "Your most recent expense was ₹{top_amount:,.0f} — {top_desc}.",

    QueryIntent.BUDGET_STATUS:
        "Budget status for this month: {summary}",

    QueryIntent.UNKNOWN:
        "I can answer questions about your spending. Try asking: "
        "\"How much did I spend this month?\" or \"What were my top expenses last month?\"",
}


class ResponseGenerator:
    """
    Stage 3: Converts structured DB query results into natural language.

    The LLM receives:
    - The user's original question
    - The intent type (for context)
    - The REAL data from the DB (numbers, lists)

    The LLM outputs:
    - A natural language answer using only the provided data

    Fallback behavior:
    - If Gemini fails → use template-based responses (still accurate, less fluent)
    - Templates are pre-computed from the data dict, no LLM needed
    """

    def __init__(self):
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config=genai.GenerationConfig(
                    temperature=0.3,       # slight creativity for natural language
                    max_output_tokens=200, # answers must be concise
                ),
            )
        else:
            self.model = None

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4), reraise=False)
    async def generate(self, result: QueryResult, original_query: str) -> str:
        """
        Generate a natural language answer from query results.

        Args:
            result: Structured data from QueryEngine
            original_query: User's original question (for context only, not for DB)

        Returns:
            Natural language answer string
        """
        # Handle unknown intent immediately — no LLM needed
        if result.intent == QueryIntent.UNKNOWN:
            return FALLBACK_TEMPLATES[QueryIntent.UNKNOWN]

        # No data found
        if not result.found_results:
            return self._no_data_response(result, original_query)

        # Try LLM response first
        if self.model:
            try:
                return await self._llm_response(result, original_query)
            except Exception as e:
                logger.warning(f"LLM response generation failed: {e}, falling back to template")

        # Template fallback
        return self._template_response(result)

    async def _llm_response(self, result: QueryResult, query: str) -> str:
        """Generate natural language using Gemini with real data injected."""
        prompt = RESPONSE_PROMPT.format(
            query=query,
            intent=result.intent.value,
            data=json.dumps(result.data, indent=2, default=str),
        )

        response = await self.model.generate_content_async(prompt)
        answer = response.text.strip()

        # Sanity check: answer shouldn't be empty or too long
        if not answer or len(answer) > 500:
            return self._template_response(result)

        return answer

    def _no_data_response(self, result: QueryResult, query: str) -> str:
        """Friendly response when no matching expenses found."""
        period = str(result.date_range)
        intent = result.intent

        if intent == QueryIntent.CATEGORY_SPEND_PERIOD:
            cat = result.data.get("category", "that category")
            return (
                f"You have no {cat} expenses recorded for {period}. "
                f"Add some expenses using the Add Expense page."
            )
        elif intent == QueryIntent.BUDGET_STATUS:
            return (
                "You haven't set any budgets yet. "
                "Go to the Budgets page to set monthly spending limits."
            )
        else:
            return (
                f"No expenses found for {period}. "
                f"Start tracking your spending using the Add Expense page."
            )

    def _template_response(self, result: QueryResult) -> str:
        """
        Pure data-driven fallback — no LLM required.
        Always produces a correct answer even if less natural.
        """
        data = result.data
        intent = result.intent
        template = FALLBACK_TEMPLATES.get(intent, FALLBACK_TEMPLATES[QueryIntent.UNKNOWN])

        try:
            match intent:
                case QueryIntent.TOTAL_SPEND_PERIOD:
                    return template.format(
                        total=data.get("total", 0),
                        count=data.get("count", 0),
                        period=data.get("period", ""),
                    )

                case QueryIntent.CATEGORY_SPEND_PERIOD:
                    return template.format(
                        total=data.get("total", 0),
                        category=data.get("category", ""),
                        period=data.get("period", ""),
                        count=data.get("count", 0),
                    )

                case QueryIntent.TOP_EXPENSES:
                    expenses = data.get("expenses", [])
                    if expenses:
                        top = expenses[0]
                        return template.format(
                            period=data.get("period", ""),
                            top_amount=top.get("amount", 0),
                            top_desc=top.get("description", "purchase"),
                        )
                    return "No expenses found."

                case QueryIntent.SPENDING_TREND:
                    change_pct = data.get("change_percent", 0)
                    return template.format(
                        current_total=data.get("current_total", 0),
                        current_period=data.get("current_period", ""),
                        previous_total=data.get("previous_total", 0),
                        previous_period=data.get("previous_period", ""),
                        change_word="increase" if data.get("is_increase") else "decrease",
                        abs_change=abs(change_pct),
                    )

                case QueryIntent.CATEGORY_COMPARISON:
                    cats = data.get("categories", [])
                    summary = ", ".join(
                        f"{c['category']}: ₹{c['total']:,.0f} ({c['percentage']}%)"
                        for c in cats[:3]
                    )
                    return template.format(period=data.get("period", ""), summary=summary)

                case QueryIntent.MERCHANT_SPEND:
                    return template.format(
                        total=data.get("total", 0),
                        merchant_query=data.get("merchant_query", "that merchant"),
                        period=data.get("period", ""),
                    )

                case QueryIntent.RECENT_EXPENSES:
                    expenses = data.get("expenses", [])
                    if expenses:
                        top = expenses[0]
                        return template.format(
                            top_amount=top.get("amount", 0),
                            top_desc=top.get("description", "purchase"),
                        )
                    return "No recent expenses found."

                case QueryIntent.BUDGET_STATUS:
                    budgets = data.get("budgets", [])
                    summary = ", ".join(
                        f"{b['category']}: {b['percentage']}% used"
                        for b in budgets[:3]
                    )
                    return template.format(summary=summary or "no budgets set")

                case _:
                    return FALLBACK_TEMPLATES[QueryIntent.UNKNOWN]

        except (KeyError, TypeError) as e:
            logger.error(f"Template formatting error: {e}")
            return "I found some data but had trouble formatting the response. Please try again."
