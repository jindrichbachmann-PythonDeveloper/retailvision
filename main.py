from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import Response
import json

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
app = FastAPI(title="RetailVision")

@app.get("/")
def root():
    body = json.dumps({"message": "RetailVision běží 🚀"}, ensure_ascii=False).encode("utf-8")
    return Response(content=body, media_type="application/json; charset=utf-8")