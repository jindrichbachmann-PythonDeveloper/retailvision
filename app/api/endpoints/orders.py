# -*- coding: utf-8 -*-
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Body, Depends
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from app.api.deps.auth import get_current_user
from app.services.pg_service import pg_fetchall, pg_fetchone, pg_exec

router = APIRouter()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/api/orders/list", response_class=JSONResponse)
def orders_list(
    limit: int = 200,
    skip: int = 0,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    user_id = int(current_user["id"])

    params = {
        "user_id": user_id,
        "limit": int(limit),
        "skip": int(skip),
    }

    where_status = ""
    if status:
        where_status = "AND status = :status"
        params["status"] = str(status)

    rows = pg_fetchall(
        f"""
        SELECT
            id,
            user_id,
            cart_session_id,
            customer_email,
            customer_bank_account,
            status,
            stripe_session_id,
            stripe_payment_intent_id,
            total_cents,
            currency,
            shipping_method,
            shipping_price_cents,
            shipped,
            shipped_at,
            created_at,
            paid_at
        FROM orders
        WHERE user_id = :user_id
        {where_status}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :skip
        """,
        params
    )

    return JSONResponse(content=jsonable_encoder(rows))


@router.get("/api/order/{order_id}", response_class=JSONResponse)
def order_get(
    order_id: int,
    current_user: dict = Depends(get_current_user)
):
    user_id = int(current_user["id"])

    order = pg_fetchone(
        """
        SELECT *
        FROM orders
        WHERE id = :order_id
          AND user_id = :user_id
        """,
        {
            "order_id": int(order_id),
            "user_id": user_id,
        }
    )

    if not order:
        raise HTTPException(status_code=404, detail="Objednávka nenalezena")

    items = pg_fetchall(
        """
        SELECT *
        FROM order_items
        WHERE order_id = :order_id
          AND user_id = :user_id
        ORDER BY id ASC
        """,
        {
            "order_id": int(order_id),
            "user_id": user_id,
        }
    )

    order["items"] = items

    return JSONResponse(content=jsonable_encoder(order))


@router.delete("/api/order/{order_id}", response_class=JSONResponse)
def order_delete(
    order_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Bezpečnost:
    - maže jen objednávku aktuálního uživatele
    - placené objednávky nemažeme
    - pokud existuje faktura, objednávku nemažeme
    """
    user_id = int(current_user["id"])

    order = pg_fetchone(
        """
        SELECT *
        FROM orders
        WHERE id = :order_id
          AND user_id = :user_id
        """,
        {
            "order_id": int(order_id),
            "user_id": user_id,
        }
    )

    if not order:
        raise HTTPException(status_code=404, detail="Objednávka nenalezena")

    if order.get("status") == "paid" or order.get("paid_at"):
        raise HTTPException(status_code=400, detail="Zaplacenou objednávku nelze smazat")

    invoice = pg_fetchone(
        """
        SELECT id
        FROM invoices
        WHERE order_id = :order_id
          AND user_id = :user_id
        LIMIT 1
        """,
        {
            "order_id": int(order_id),
            "user_id": user_id,
        }
    )

    if invoice:
        raise HTTPException(status_code=400, detail="Objednávku s fakturou nelze smazat")

    pg_exec(
        """
        DELETE FROM orders
        WHERE id = :order_id
          AND user_id = :user_id
        """,
        {
            "order_id": int(order_id),
            "user_id": user_id,
        }
    )

    return {"ok": True, "deleted_id": int(order_id)}


@router.post("/api/order/ship/{order_id}", response_class=JSONResponse)
def order_ship(
    order_id: int,
    data: Dict[str, Any] = Body(default={}),
    current_user: dict = Depends(get_current_user)
):
    user_id = int(current_user["id"])

    order = pg_fetchone(
        """
        SELECT *
        FROM orders
        WHERE id = :order_id
          AND user_id = :user_id
        """,
        {
            "order_id": int(order_id),
            "user_id": user_id,
        }
    )

    if not order:
        raise HTTPException(status_code=404, detail="Objednávka nenalezena")

    carrier = (data.get("carrier") or "").strip()
    tracking = (data.get("tracking") or "").strip()

    pg_exec(
        """
        UPDATE orders
        SET
            shipped = TRUE,
            shipped_at = now(),
            status = 'odeslano'
        WHERE id = :order_id
          AND user_id = :user_id
        """,
        {
            "order_id": int(order_id),
            "user_id": user_id,
        }
    )

    return {
        "ok": True,
        "order_id": int(order_id),
        "shipped": True,
        "carrier": carrier,
        "tracking": tracking
    }


@router.post("/api/orders/cleanup", response_class=JSONResponse)
def orders_cleanup(
    data: Dict[str, Any] = Body(default={}),
    current_user: dict = Depends(get_current_user)
):
    """
    Maže jen nezaplacené / zrušené objednávky aktuálního uživatele.
    Faktury a zaplacené objednávky nemaže.
    """
    user_id = int(current_user["id"])

    days = int(data.get("days", 30))

    pg_exec(
        """
        DELETE FROM orders
        WHERE user_id = :user_id
          AND created_at < (now() - (:days || ' days')::interval)
          AND status IN ('nova', 'cancel', 'storno', 'zruseno', 'pending')
          AND paid_at IS NULL
          AND id NOT IN (
              SELECT order_id
              FROM invoices
              WHERE user_id = :user_id
          )
        """,
        {
            "user_id": user_id,
            "days": days,
        }
    )

    return {"ok": True, "days": days}


@router.post("/api/orders/clear_all", response_class=JSONResponse)
def orders_clear_all(
    current_user: dict = Depends(get_current_user)
):
    """
    DEBUG:
    Už nemažeme celou databázi.
    Mažeme jen nezaplacené objednávky aktuálního uživatele bez faktury.
    """
    user_id = int(current_user["id"])

    pg_exec(
        """
        DELETE FROM orders
        WHERE user_id = :user_id
          AND paid_at IS NULL
          AND id NOT IN (
              SELECT order_id
              FROM invoices
              WHERE user_id = :user_id
          )
        """,
        {
            "user_id": user_id,
        }
    )

    return {"ok": True}