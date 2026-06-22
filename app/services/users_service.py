import random
import string
from typing import Dict, Any, List, Optional

import bcrypt
from fastapi import HTTPException

from app.services.pg_service import pg_fetchone, pg_fetchall, pg_exec

def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def _rand_suffix(n: int = 6) -> str:
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))

def seed_users(n: int = 10, default_password: str = "test1234") -> Dict[str, Any]:
    if n <= 0:
        raise HTTPException(400, "n musí být > 0")
    if len(default_password) < 6:
        raise HTTPException(400, "default_password musí mít aspoň 6 znaků")

    inserted = 0
    created: List[Dict[str, Any]] = []

    for i in range(int(n)):
        username = f"user{i+1}_{_rand_suffix()}"
        email = f"{username}@example.com"
        ph = _hash_password(default_password)

        try:
            row = pg_fetchone(
                """
                INSERT INTO users (username, email, pass_hash, role, is_active)
                VALUES (:u, :e, :ph, 'user', TRUE)
                RETURNING id, username, email, role, is_active
                """,
                {"u": username, "e": email, "ph": ph}
            )
            inserted += 1
            created.append({
                "id": int(row["id"]),
                "username": row["username"],
                "email": row.get("email"),
                "role": row.get("role"),
                "is_active": bool(row.get("is_active", True))
            })
        except Exception:
            # když narazíme na unikát (username/email), zkusíme další
            continue

    return {"ok": True, "inserted": inserted, "default_password": default_password, "users": created}

def list_users(limit: int = 200, skip: int = 0) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    skip = max(0, int(skip))

    rows = pg_fetchall(
        """
        SELECT id, username, email, role, is_active
        FROM users
        ORDER BY id DESC
        LIMIT :limit OFFSET :skip
        """,
        {"limit": limit, "skip": skip}
    )

    out = []
    for r in rows:
        out.append({
            "id": int(r["id"]),
            "username": r["username"],
            "email": r.get("email"),
            "role": r.get("role"),
            "is_active": bool(r.get("is_active", True))
        })
    return out

def random_user() -> Dict[str, Any]:
    row = pg_fetchone(
        """
        SELECT id, username, email, role, is_active
        FROM users
        ORDER BY random()
        LIMIT 1
        """
    )
    if not row:
        raise HTTPException(404, "Žádní uživatelé v DB")
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "email": row.get("email"),
        "role": row.get("role"),
        "is_active": bool(row.get("is_active", True))
    }


