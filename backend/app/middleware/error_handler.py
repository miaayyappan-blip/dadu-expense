import time
import uuid
import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


async def request_logging_middleware(request: Request, call_next):
    """
    Logs every request with timing and a unique request ID.
    request_id is included in responses so frontend can correlate errors.
    """
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    logger.info(f"[{request_id}] {request.method} {request.url.path} started")

    response = await call_next(request)
    duration = round((time.time() - start_time) * 1000, 2)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration}ms"

    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"completed {response.status_code} in {duration}ms"
    )
    return response


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Transform Pydantic validation errors into a clean, consistent shape."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation failed", "errors": errors},
    )


async def integrity_error_handler(request: Request, exc: IntegrityError):
    """Handle DB-level constraint violations gracefully."""
    logger.error(f"Database integrity error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "A record with this data already exists"},
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all: never expose internal stack traces to clients."""
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please try again."},
    )
