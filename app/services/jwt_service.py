# -*- coding: utf-8 -*-
import os
from typing import Dict, Any
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError, ExpiredSignatureError
from fastapi import HTTPException

JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
JWT_ALG = os.getenv("JWT_ALG", "HS256").strip() or "HS256"
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "120"))


def create_access_token(
    sub: str,
    role: str,
    user_id: int,
    expires_min: int = JWT_EXPIRE_MIN,
) -> str:

    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET není nastaven")

    now = datetime.now(timezone.utc)

    payload = {
        "sub": sub,
        "role": role,
        "uid": int(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_min)).timestamp()),
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> Dict[str, Any]:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET není nastaven")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

        if not isinstance(payload, dict):
            raise HTTPException(status_code=401, detail="Neplatný token")

        return payload

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token vypršel")

    except JWTError:
        raise HTTPException(status_code=401, detail="Neplatný token")