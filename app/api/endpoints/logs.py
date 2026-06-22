from fastapi import APIRouter
from typing import Optional
from app.services.mongo_ctx import col_logs

router = APIRouter()

@router.get("/api/logs/")
def logs_list(limit: int = 200, skip: int = 0, level: Optional[str] = None):
    query = {}
    if level:
        query["level"] = str(level)

    cur = col_logs().find(query).skip(skip).limit(limit).sort("_id", -1)
    out = []
    for d in cur:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out
