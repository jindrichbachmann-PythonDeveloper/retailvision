from typing import Dict, Any, Optional
from datetime import datetime
from bson import ObjectId
from fastapi import HTTPException

from app.services.mongo_ctx import col_orders
from app.services.log_event_service import log_event

def mark_order_paid(order_id: str, stripe_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Neplatné order_id")

    order = col_orders().find_one({"_id": oid})
    if not order:
        raise HTTPException(status_code=404, detail="Order nenalezen")

    now = datetime.utcnow()
    upd = {
        "paid": True,
        "paid_at": now,
        "status": "paid",
    }

    if stripe_data and isinstance(stripe_data, dict):
        # uložíme, co přijde (session_id, payment_intent, customer, ...)
        upd["stripe"] = stripe_data

    col_orders().update_one({"_id": oid}, {"": upd})

    log_event("info", "Stripe checkout success", {"order_id": order_id, "stripe": stripe_data or {}})

    return {
        "ok": True,
        "order_id": order_id,
        "paid": True,
        "paid_at": now.isoformat(),
    }
