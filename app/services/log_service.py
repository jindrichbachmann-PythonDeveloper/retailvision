from typing import Any, Dict

def log_event(level: str, msg: str, data: Dict[str, Any] | None = None):
    # jednoduchý logger (monolit má bohatší)
    try:
        print(f"[{level.upper()}] {msg} | {data or {}}")
    except Exception:
        pass
