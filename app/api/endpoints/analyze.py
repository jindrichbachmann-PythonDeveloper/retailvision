from fastapi import APIRouter, UploadFile, File, Query, Depends
from typing import List
from fastapi.responses import Response
from fastapi.encoders import jsonable_encoder
from app.services.auth_service import get_current_user
import json

from app.services.analyze_service import analyze_files

router = APIRouter()

@router.post("/api/analyze/")
async def analyze(
    files: List[UploadFile] = File(...),
    use_ai_filter: int = Query(1),
    recognize: int = Query(1),
    user=Depends(get_current_user),
):
    result = await analyze_files(
        files,
        use_ai_filter=use_ai_filter,
        recognize=recognize,
        user=user,
    )
    body = json.dumps(jsonable_encoder(result), ensure_ascii=False).encode("utf-8")
    return Response(content=body, media_type="application/json; charset=utf-8")
