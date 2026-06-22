# -*- coding: utf-8 -*-
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

# app/api/endpoints/web.py -> app/
APP_DIR = Path(__file__).resolve().parents[2]

# app/web/templates/
TEMPLATES_DIR = APP_DIR / "web" / "templates"


def load_html(name: str) -> str:
    path = TEMPLATES_DIR / name

    print(f"📄 Načítám HTML: {path}")
    print(f"📄 Existuje: {path.exists()}")

    if not path.exists():
        return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <title>Soubor nenalezen</title>
</head>
<body>
  <h1>❌ Soubor nenalezen</h1>
  <p>Chybí soubor: <strong>{name}</strong></p>
  <pre>{path}</pre>
</body>
</html>"""

    return path.read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
def web_root():
    return HTMLResponse(
        content=load_html("index.html"),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/login", response_class=HTMLResponse)
def login():
    return HTMLResponse(
        content=load_html("login.html"),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/register", response_class=HTMLResponse)
def register():
    return HTMLResponse(
        content=load_html("register.html"),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/forgot", response_class=HTMLResponse)
def forgot():
    return HTMLResponse(
        content=load_html("forgot.html"),
        headers={"Cache-Control": "no-store"},
    )