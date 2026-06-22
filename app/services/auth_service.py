# -*- coding: utf-8 -*-
import os
import smtplib
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import bcrypt
from fastapi import HTTPException, Request
from email.mime.text import MIMEText
from dotenv import load_dotenv

from app.services.jwt_service import create_access_token, decode_access_token
from app.services.pg_service import pg_fetchone, pg_exec
from app.core.logging import log_event

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASS = os.getenv("SMTP_PASS", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def forgot_password(email: str) -> Dict[str, Any]:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Zadej platný e-mail.")

    row = pg_fetchone(
        "SELECT id, username, is_active FROM users WHERE lower(email)=:e",
        {"e": email},
    )

    if not row:
        return {
            "ok": True,
            "message": "Pokud e-mail existuje v systému, byl odeslán odkaz na obnovu hesla.",
        }

    token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(token)
    exp = datetime.utcnow() + timedelta(minutes=30)

    pg_exec(
        """
        UPDATE users
        SET reset_token_hash=:h, reset_token_expires=:exp
        WHERE id=:id
        """,
        {"h": token_hash, "exp": exp, "id": row["id"]},
    )

    if SMTP_HOST and SMTP_FROM:
        reset_link = f"{PUBLIC_BASE_URL}/reset?token={token}"
        body = f"""Dobrý den,

požádal/a jste o obnovu hesla.

Odkaz pro změnu hesla (platnost 30 minut):
{reset_link}

Pokud jste o obnovu nežádal/a, tento e-mail ignorujte.

S pozdravem
Hodinářství Jindra
"""

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "Obnova hesla – Hodinářství Jindra"
        msg["From"] = SMTP_FROM
        msg["To"] = email

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
                s.ehlo()
                if SMTP_USER and SMTP_PASS:
                    s.starttls()
                    s.ehlo()
                    s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(SMTP_FROM, [email], msg.as_string())
        except Exception as e:
            log_event("error", f"Forgot email send failed: {e}", {"email": email})

    return {
        "ok": True,
        "message": "Pokud e-mail existuje v systému, byl odeslán odkaz na obnovu hesla.",
    }


def reset_password(token: str, new_password: str) -> Dict[str, Any]:
    token = (token or "").strip()
    newp = new_password or ""

    if len(newp) < 6:
        raise HTTPException(400, "Nové heslo musí mít aspoň 6 znaků.")
    if not token:
        raise HTTPException(400, "Chybí token.")

    h = _hash_reset_token(token)

    row = pg_fetchone(
        """
        SELECT id, reset_token_expires
        FROM users
        WHERE reset_token_hash=:h
        """,
        {"h": h},
    )

    if not row:
        raise HTTPException(400, "Token je neplatný.")

    exp = row.get("reset_token_expires")
    if not exp:
        raise HTTPException(400, "Token je neplatný.")

    if datetime.utcnow() > exp.replace(tzinfo=None):
        raise HTTPException(400, "Token vypršel.")

    pg_exec(
        """
        UPDATE users
        SET pass_hash=:ph,
            reset_token_hash=NULL,
            reset_token_expires=NULL
        WHERE id=:id
        """,
        {"ph": _hash_password(newp), "id": row["id"]},
    )

    return {"ok": True, "message": "Heslo bylo změněno."}


def register_user(username: str, password: str) -> Dict[str, Any]:
    u = (username or "").strip()
    p = password or ""

    if len(u) < 3:
        raise HTTPException(400, "Uživatelské jméno musí mít aspoň 3 znaky.")
    if len(p) < 6:
        raise HTTPException(400, "Heslo musí mít aspoň 6 znaků.")

    trial_until = datetime.utcnow() + timedelta(days=7)

    try:
        row = pg_fetchone(
            """
            INSERT INTO users (username, pass_hash, role, is_active, trial_until, subscription_active)
            VALUES (:u, :ph, 'user', TRUE, :trial_until, FALSE)
            RETURNING id, username, role, is_active, trial_until
            """,
            {
                "u": u,
                "ph": _hash_password(p),
                "trial_until": trial_until,
            },
        )
    except Exception:
        raise HTTPException(409, "Uživatelské jméno je už obsazené.")

    return {
        "ok": True,
        "message": "Účet byl založen. Zkušební doba je 7 dní.",
        "user": row,
    }


def token_login(username: str, password: str) -> Dict[str, Any]:
    row = pg_fetchone(
        """
        SELECT id, username, email, pass_hash, role, is_active
        FROM users
        WHERE username = :username
        """,
        {"username": username},
    )

    if not row:
        raise HTTPException(status_code=401, detail="Neplatné přihlašovací údaje")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Účet je deaktivován")

    if not bcrypt.checkpw(password.encode("utf-8"), row["pass_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Neplatné přihlašovací údaje")

    role = (row.get("role") or "user").lower()
    expires_min = 120 if role == "admin" else 30

    access_token = create_access_token(
        sub=row["username"],
        role=row["role"],
        user_id=row["id"],
        expires_min=expires_min,
    )

    return {
        "ok": True,
        "access_token": access_token,
        "token_type": "bearer",
        "expires_minutes": expires_min,
        "user": {
            "id": row["id"],
            "uid": str(row["id"]),
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
        },
    }

def login_user(username: str, password: str) -> Dict[str, Any]:
    return token_login(username, password)

def resolve_current_user_from_token(token: str) -> Dict[str, Any]:
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Chybí Bearer token")

    data = decode_access_token(token)
    username = data.get("sub")

    if not username:
        raise HTTPException(status_code=401, detail="Token nemá sub")

    row = pg_fetchone(
        """
        SELECT id, username, email, role, is_active, trial_until, subscription_active
        FROM users
        WHERE username = :u
        """,
        {"u": username},
    )

    if not row:
        raise HTTPException(status_code=401, detail="Uživatel neexistuje")

    if not row.get("is_active"):
        raise HTTPException(status_code=403, detail="Účet je deaktivován")

    role = (row.get("role") or "").strip().lower()

    if role != "admin":
        trial_until = row.get("trial_until")
        subscription_active = bool(row.get("subscription_active"))

        if not subscription_active:
            if not trial_until:
                raise HTTPException(status_code=403, detail="Vyčerpal jsi 7denní limit")

            try:
                trial_until_naive = trial_until.replace(tzinfo=None)
            except Exception:
                trial_until_naive = trial_until

            if datetime.utcnow() > trial_until_naive:
                raise HTTPException(status_code=403, detail="Vyčerpal jsi 7denní limit")

    return {
        "id": row["id"],
        "uid": str(row["id"]),
        "username": row["username"],
        "email": row.get("email"),
        "role": row.get("role"),
        "is_active": row.get("is_active"),
        "trial_until": row.get("trial_until"),
        "subscription_active": row.get("subscription_active"),
        "token_payload": data,
    }


def _extract_bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization") or ""

    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Chybí Bearer token")

    return auth.split(" ", 1)[1].strip()


def get_current_user(request: Request) -> Dict[str, Any]:
    token = _extract_bearer_token(request)
    return resolve_current_user_from_token(token)


def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    try:
        token = _extract_bearer_token(request)
        return resolve_current_user_from_token(token)
    except Exception:
        return None