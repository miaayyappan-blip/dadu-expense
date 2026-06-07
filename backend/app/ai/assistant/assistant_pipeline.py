import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.assistant.intent_classifier import IntentClassifier, QueryIntent
from app.ai.assistant.query_engine import QueryEngine, QueryResult
from app.ai.assistant.response_generator import ResponseGenerator

logger = logging.getLogger(__name__)


@dataclass
class AssistantResult:
    """Full result of the assistant pipeline."""
    answer: str                        # Natural language response shown to user
    query_type: str                    # Intent name for frontend display
    data: dict[str, Any]              # Raw data (for frontend to optionally render)
    confidence: float                  # Classification confidence
    was_understood: bool               # False if intent = UNKNOWN


class AssistantPipeline:
    """
    Three-stage NL → Data → Answer pipeline.

    Stage 1 — Classify:    LLM maps query to intent + parameters
    Stage 2 — Query:       Safe parameterized DB query (no LLM)
    Stage 3 — Respond:     LLM formats real data into natural language

    Security model summary:
    - User text only reaches Stage 1 (classification)
    - Stage 1 outputs only closed-enum values — validated by Pydantic
    - Stage 2 uses those enum values to select a pre-written query template
    - user_id is injected at the service layer, never from LLM output
    - Stage 3 receives real DB numbers — LLM cannot fabricate figures

    Performance: ~1.5–2.5 seconds total (2 LLM calls + 1 DB query)
    """

    # Queries we won't attempt to answer
    REJECTION_RESPONSES = {
        QueryIntent.UNKNOWN: (
            "I can help with questions about your expenses. Try:\n"
            "• \"How much did I spend this month?\"\n"
            "• \"What's my biggest expense category?\"\n"
            "• \"Compare my food and transport spending\"\n"
            "• \"Am I over budget on shopping?\""
        )
    }

    def __init__(self):
        self.classifier = IntentClassifier()
        self.response_gen = ResponseGenerator()

    async def run(
        self,
        query: str,
        user_id: int,
        db: AsyncSession,
    ) -> AssistantResult:
        """
        Process a natural language expense query end-to-end.

        Args:
            query:   Raw user input (untrusted)
            user_id: Authenticated user's ID (from JWT, not from query)
            db:      Async DB session

        Returns:
            AssistantResult with answer and supporting data
        """
        # ── Stage 1: Intent classification ───────────────────────────────────
        logger.info(f"Assistant query from user {user_id}: '{query[:80]}'")

        try:
            intent = await self.classifier.classify(query)
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return AssistantResult(
                answer="I'm having trouble understanding that. Please try rephrasing your question.",
                query_type="error",
                data={},
                confidence=0.0,
                was_understood=False,
            )

        logger.info(f"Classified as: {intent.intent.value} (confidence={intent.classification_confidence:.2f})")

        # Reject unknown intents immediately
        if intent.intent == QueryIntent.UNKNOWN:
            return AssistantResult(
                answer=self.REJECTION_RESPONSES[QueryIntent.UNKNOWN],
                query_type="unknown",
                data={},
                confidence=intent.classification_confidence,
                was_understood=False,
            )

        # ── Stage 2: Safe DB query ────────────────────────────────────────────
        engine = QueryEngine(db)
        try:
            result: QueryResult = await engine.execute(intent, user_id)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return AssistantResult(
                answer="I found your question but had trouble fetching the data. Please try again.",
                query_type=intent.intent.value,
                data={},
                confidence=intent.classification_confidence,
                was_understood=True,
            )

        # ── Stage 3: Natural language response ───────────────────────────────
        try:
            answer = await self.response_gen.generate(result, query)
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            # Fall back to raw data representation
            answer = f"I found data for your query but had trouble formatting it: {result.data}"

        logger.info(f"Assistant responded: '{answer[:100]}'")

        return AssistantResult(
            answer=answer,
            query_type=intent.intent.value,
            data=result.data,
            confidence=intent.classification_confidence,
            was_understood=True,
        )
