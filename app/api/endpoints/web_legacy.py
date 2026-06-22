from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

# 1:1: stejné HTML jako homepage (WEB_HTML)
try:
    from app.web.pages import WEB_HTML
except Exception as e:
    WEB_HTML = f"<h1>Chybí app.web.pages</h1><pre>{e}</pre>"

@router.get("/web/", response_class=HTMLResponse)
def web_legacy():
    return HTMLResponse(WEB_HTML)
