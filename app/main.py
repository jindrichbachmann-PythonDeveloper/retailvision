# -*- coding: utf-8 -*-
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# --- load .env (1:1, robust) ---
try:
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parents[1]  # .../retailvision
    print("📁 Načítám .env z:", _ROOT / ".env")
    load_dotenv(dotenv_path=_ROOT / ".env")
    print("✅ .env načteno")
except Exception as _e:
    print(f"[WARN] dotenv load failed: {_e}")
    _ROOT = Path(__file__).resolve().parents[1]

print("🔧 CWD:", os.getcwd())
print("📧 ACCOUNTANT_EMAIL:", os.getenv("ACCOUNTANT_EMAIL"))

from app.api.router import api_router
print("📦 Import API router OK")

from app.middleware.access_guard import access_guard_middleware
print("🛡️ Access guard načten")

from fastapi.security import HTTPBearer
app = FastAPI(
    title="RetailVision",
    swagger_ui_parameters={"persistAuthorization": True}
)
print("🚀 FastAPI vytvořena")

from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="RetailVision",
        version="1.0.0",
        description="API",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    openapi_schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# --- templates ---
TEMPLATES_DIR = _ROOT / "app" / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
print("🌐 Templates složka:", TEMPLATES_DIR)

# ---- Access guard middleware (1:1) ----
app.middleware("http")(access_guard_middleware)
print("🛡️ Middleware připojen")

# ---- výpisy do konzole (REQ/RES) ----
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"[REQ] {request.method} {request.url.path}")
    resp = await call_next(request)
    print(f"[RES] {request.method} {request.url.path} -> {resp.status_code}")
    return resp

# API
app.include_router(api_router)
print("🔗 Router připojen")

print("✅ hotovo – čekám na další pokyn")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
def register(request: Request):
    return templates.TemplateResponse("registr.html", {"request": request})


@app.get("/forgot", response_class=HTMLResponse)
def forgot(request: Request):
    return templates.TemplateResponse("forgor.html", {"request": request})


@app.head("/")
async def head_root():
    return Response(status_code=200)