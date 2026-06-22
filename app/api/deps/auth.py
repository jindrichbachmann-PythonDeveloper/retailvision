# -*- coding: utf-8 -*-
from typing import Dict, Any

from fastapi import Request, HTTPException


def get_current_user(request: Request) -> Dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Nepřihlášený uživatel")
    return user


def require_admin(request: Request) -> Dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Nepřihlášený uživatel")

    role = (user.get("role") or "").strip().lower()
    if role != "admin":
        raise HTTPException(status_code=403, detail="Vyžadována role admin")

    return user