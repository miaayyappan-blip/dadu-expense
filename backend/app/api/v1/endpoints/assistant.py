import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.assistant.assistant_pipeline import AssistantPipeline
from app.core.dependencies import get_current_active_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.dashboard import AssistantQueryRequest, AssistantQueryResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assistant", tags=["AI Assistant"])

# Module-level singleton — classifier + response gen initialized once
_pipeline: AssistantPipeline | None = None


def get_pipeline() -> AssistantPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = AssistantPipeline()
    return _pipeline


@router.post(
    "/query",
    response_model=AssistantQueryResponse,
    summary="Ask a natural language question about your expenses",
    description=(
        "Accepts a natural language query. "
        "Classifies intent → executes safe DB query → returns natural language answer. "
        "The user's text never directly influences SQL generation."
    ),
)
async def query_assistant(
    request: AssistantQueryRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AssistantQueryResponse:
    """
    Security checklist:
    - user_id comes from JWT (get_current_active_user) — not from request body
    - query is truncated to 500 chars in the classifier — prevents prompt injection via length
    - intent must match a closed enum — unknown queries are rejected before any DB access
    - all DB queries use SQLAlchemy parameters — no f-string SQL
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty",
        )

    if len(request.query) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query too long (max 500 characters)",
        )

    pipeline = get_pipeline()
    result = await pipeline.run(
        query=request.query,
        user_id=current_user.id,
        db=db,
    )

    return AssistantQueryResponse(
        answer=result.answer,
        data=result.data if result.was_understood else None,
        query_type=result.query_type,
    )
