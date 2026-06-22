from typing import Optional, Dict, Any
from datetime import datetime, timezone

from app.services.mongo_ctx import col_logs

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def log_event(level: str, message: str, data: Optional[Dict[str, Any]] = None):
    try:
        col_logs().insert_one({
            "ts": now_utc_iso(),
            "level": level,
            "message": message,
            "data": data or {},
        })
    except Exception as e:
        print("log_event failed:", repr(e), level, message)
