# -*- coding: utf-8 -*-
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/api/health", response_class=JSONResponse)
def api_health():
    return {"status": "ok"}

# alias (necháme kvůli kompatibilitě)
@router.get("/health", response_class=JSONResponse)
def health():
    return {"status": "ok"}
