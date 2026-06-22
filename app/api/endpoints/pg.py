# -*- coding: utf-8 -*-
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.pg_service import pg_fetchone

router = APIRouter()

@router.get("/api/pg/ping", response_class=JSONResponse)
def pg_ping():
    try:
        row = pg_fetchone("SELECT current_database() AS db, 1 AS ping", {})
        return {"ok": True, "db": row.get("db"), "ping": int(row.get("ping", 1))}
    except Exception as e:
        return JSONResponse({"detail": f"PG ping failed: {e}"}, status_code=500)
