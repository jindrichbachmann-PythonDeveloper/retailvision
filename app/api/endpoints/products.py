# -*- coding: utf-8 -*-

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_service import get_current_user
from app.services.pg_service import pg_fetchone, pg_exec

router = APIRouter()


class ProductUpdate(BaseModel):
    name: str
    description: str = ""
    price_cents: int = 0


@router.post("/api/product/update/{mongo_item_id}")
def update_product(
    mongo_item_id: str,
    body: ProductUpdate,
    user=Depends(get_current_user),
):
    row = pg_fetchone(
        """
        SELECT
            id,
            user_id
        FROM products
        WHERE mongo_item_id = :mongo_item_id
        LIMIT 1
        """,
        {
            "mongo_item_id": mongo_item_id,
        }
    )

    if not row:
        raise HTTPException(status_code=404, detail="Produkt nenalezen")

    if str(row["user_id"]) != str(user["uid"]):
        raise HTTPException(status_code=403, detail="Produkt nepatří uživateli")

    details_ok = (
        len((body.name or "").strip()) >= 3
        and len((body.description or "").strip()) >= 5
    )

    price_ok = body.price_cents > 0

    ready = details_ok and price_ok

    pg_exec(
        """
        UPDATE products
        SET
            name = :name,
            description = :description,
            price_cents = :price_cents,
            manually_edited = TRUE,
            details_confidence = :details_confidence,
            price_confidence = :price_confidence,
            is_ready_for_sale = :is_ready_for_sale,
            updated_at = now()
        WHERE mongo_item_id = :mongo_item_id
        """,
        {
            "mongo_item_id": mongo_item_id,
            "name": body.name.strip(),
            "description": body.description.strip(),
            "price_cents": body.price_cents,
            "details_confidence": 100 if details_ok else 0,
            "price_confidence": 100 if price_ok else 0,
            "is_ready_for_sale": ready,
        }
    )

    return {
        "ok": True,
        "is_ready_for_sale": ready,
    }