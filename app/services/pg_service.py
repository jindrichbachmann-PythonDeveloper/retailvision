# --- load .env (1:1, robust) ---
try:
    from pathlib import Path
    from dotenv import load_dotenv
    _ROOT = Path(__file__).resolve().parents[2]  # .../retailvision
    load_dotenv(dotenv_path=_ROOT / ".env")
except Exception as _e:
    print(f"[WARN] dotenv load failed (pg_service): {_e}")

import os
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "").strip()
_pg_engine: Engine | None = None

def get_pg_engine() -> Engine:
    global _pg_engine
    if _pg_engine is not None:
        return _pg_engine
    if not POSTGRES_DSN:
        raise RuntimeError("POSTGRES_DSN není nastaven v .env")

    _pg_engine = create_engine(
        POSTGRES_DSN,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    return _pg_engine

def pg_exec(sql: str, params: dict | None = None) -> None:
    eng = get_pg_engine()
    with eng.begin() as con:
        con.execute(text(sql), params or {})

def pg_fetchall(sql: str, params: dict | None = None) -> List[Dict[str, Any]]:
    eng = get_pg_engine()
    with eng.connect() as con:
        res = con.execute(text(sql), params or {})
        rows = res.mappings().all()
        return [dict(r) for r in rows]

def pg_fetchone(sql: str, params: dict | None = None) -> Optional[Dict[str, Any]]:
    eng = get_pg_engine()
    with eng.begin() as con:
        res = con.execute(text(sql), params or {})
        row = res.mappings().first()
        return dict(row) if row else None

