from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.expenses import router as expenses_router
from app.api.v1.endpoints.dashboard import router as dashboard_router
from app.api.v1.endpoints.voice import router as voice_router
from app.api.v1.endpoints.ocr import router as ocr_router
from app.api.v1.endpoints.assistant import router as assistant_router
from app.api.v1.endpoints.export import router as export_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(expenses_router)
api_router.include_router(dashboard_router)
api_router.include_router(voice_router)
api_router.include_router(ocr_router)
api_router.include_router(assistant_router)
api_router.include_router(export_router)
