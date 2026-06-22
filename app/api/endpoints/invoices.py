# -*- coding: utf-8 -*-
from typing import Dict, Any
from fastapi import APIRouter, Body, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.api.deps.auth import get_current_user
from app.services.invoice_csv_service import (
    get_invoice_config,
    set_invoice_base_dir,
    get_invoice_csv_file,
    generate_invoice,
    _get_invoice_csv_path,
    _send_csv_to_accountant,
)

from datetime import datetime
import os

router = APIRouter()

@router.get("/api/invoices/config", response_class=JSONResponse)
def api_get_invoice_config(user=Depends(get_current_user)):
    return get_invoice_config()

@router.post("/api/invoices/config", response_class=JSONResponse)
def api_set_invoice_config(
    data: Dict[str, Any] = Body(...),
    user=Depends(get_current_user),
):
    base_dir = (data.get("base_dir") or "").strip()
    return set_invoice_base_dir(base_dir)

@router.get("/api/invoices/csv/{year}/{month}")
def api_get_invoice_csv(year: int, month: int, user=Depends(get_current_user)):
    return get_invoice_csv_file(year, month)

@router.post("/api/invoices/send_to_accountant", response_class=JSONResponse)
def api_send_invoices_to_accountant(
    data: Dict[str, Any] = Body(...),
    user=Depends(get_current_user),
):
    year = int(data.get("year", 0))
    month = int(data.get("month", 0))
    if not (year and 1 <= month <= 12):
        raise HTTPException(status_code=400, detail="Musí být zadán platný rok a měsíc")

    base_date = datetime(year, month, 1)
    csv_path = _get_invoice_csv_path(base_date)
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail=f"Pro {month}.{year} žádný CSV soubor neexistuje.")

    _send_csv_to_accountant(csv_path, year, month)
    return {"ok": True, "year": year, "month": month, "csv": csv_path}

@router.post("/api/invoice/{order_id}", response_class=JSONResponse)
def api_generate_invoice(order_id: str, user=Depends(get_current_user)):
    return generate_invoice(order_id)