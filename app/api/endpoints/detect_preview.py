from fastapi import APIRouter, UploadFile, File, Header
from typing import Optional
from fastapi.responses import JSONResponse

from app.services.preview_service import detect_preview_logic

router = APIRouter()

@router.post("/api/detect_preview", response_class=JSONResponse)
async def detect_preview(
    file: UploadFile = File(...),
    x_session_id: Optional[str] = Header(None),
):
    raw = await file.read()
    session_id = (x_session_id or "").strip() or "default"
    result = await detect_preview_logic(raw, session_id)
    return JSONResponse(result)
