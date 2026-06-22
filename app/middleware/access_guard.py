# -*- coding: utf-8 -*-
import os
from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.auth_service import resolve_current_user_from_token


# --- ENV konfigurace ---
GUARD_ENABLED = os.getenv("GUARD_ENABLED", "1").strip() not in ("0", "false", "False")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").strip()

# veřejné prefixy
PUBLIC_PREFIXES = (
    "/",
    "/login",
    "/register",
    "/forgot",
    "/reset",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/web/",
    "/static/",
)

PUBLIC_API_PREFIXES = (
    # auth
    "/api/auth/login",
    "/api/auth/token",
    "/api/auth/register",
    "/api/auth/forgot",
    "/api/auth/reset",

    # veřejný zákaznický obchod
    "/api/health",
    "/api/status",
    "/api/list",
    "/api/image/",
    "/api/cart",
    "/api/stripe",
)

# pokud chceš některé endpointy záměrně veřejné, přidej je sem
PUBLIC_API_EXACT = {
    "/api/health",
}


def _host_ok(host: str) -> bool:
    if not ALLOWED_HOSTS:
        return True

    host = (host or "").split(":")[0].strip().lower()
    allowed = [h.strip().lower() for h in ALLOWED_HOSTS.split(",") if h.strip()]
    return host in allowed


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_API_EXACT:
        return True

    if path.startswith(PUBLIC_API_PREFIXES):
        return True

    # root řešíme zvlášť, aby "/" neodemklo všechno
    if path == "/":
        return True

    for prefix in PUBLIC_PREFIXES:
        if prefix == "/":
            continue
        if path.startswith(prefix):
            return True

    return False


def _extract_bearer(auth_header: str) -> str:
    auth = (auth_header or "").strip()
    if not auth:
        return ""

    parts = auth.split(" ", 1)
    if len(parts) != 2:
        return ""

    scheme, token = parts[0].strip(), parts[1].strip()
    if scheme.lower() != "bearer":
        return ""

    return token


async def access_guard_middleware(request: Request, call_next):
    if not GUARD_ENABLED:
        return await call_next(request)

    path = request.url.path
    host = request.headers.get("host", "")

    # 1) host guard
    if not _host_ok(host):
        return JSONResponse({"detail": "Host není povolen"}, status_code=403)

    # 2) public path bypass
    if _is_public_path(path):
        return await call_next(request)

    # 3) bearer token z headeru
    auth = request.headers.get("authorization", "")
    token = _extract_bearer(auth)

    if not token:
        return JSONResponse({"detail": "Chybí Bearer token"}, status_code=401)

    # 4) centrální auth resolve
    try:
        user = resolve_current_user_from_token(token)
        request.state.user = user
    except Exception as e:
        status_code = getattr(e, "status_code", 401)
        detail = getattr(e, "detail", "Neplatný nebo expirovaný token")
        return JSONResponse({"detail": detail}, status_code=status_code)

    # 5) pustit request dál
    return await call_next(request)