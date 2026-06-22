# -*- coding: utf-8 -*-
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# 1:1: logujeme do stejné Mongo kolekce event_logs
# (col_logs je v mongo_ctx, používá se i jinde)
try:
    from app.services.mongo_ctx import col_logs
except Exception as e:
    col_logs = None
    print("⚠️ logging.py: nelze importovat col_logs:", repr(e))

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def log_event(level: str, message: str, data: Optional[Dict[str, Any]] = None):
    # 1:1: nikdy neshodit app kvůli logům
    try:
        if col_logs is None:
            print(f"[LOG:{level}] {message} {data or {}}")
            return

        col_logs().insert_one({
            "ts": now_utc_iso(),
            "level": level,
            "message": message,
            "data": data or {},
        })
    except Exception as e:
        print("log_event failed:", repr(e), level, message, data)
