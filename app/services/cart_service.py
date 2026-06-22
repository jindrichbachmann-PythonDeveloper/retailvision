from typing import Dict, Any, List, Optional
from datetime import datetime
from bson import ObjectId

from fastapi import HTTPException

from app.services.mongo_ctx import get_db, col_items, col_orders
from app.services.log_event_service import log_event

def _cart_col():
    return get_db()['cart']

def get_cart(session_id: str) -> Dict[str, Any]:
    sid = (session_id or '').strip() or 'default'
    doc = _cart_col().find_one({'_id': sid})
    if not doc:
        doc = {'_id': sid, 'items': [], 'updated': datetime.utcnow()}
        _cart_col().insert_one(doc)
    doc['_id'] = str(doc['_id'])
    return doc

def clear_cart(session_id: str) -> Dict[str, Any]:
    sid = (session_id or '').strip() or 'default'
    _cart_col().update_one({'_id': sid}, {'': {'items': [], 'updated': datetime.utcnow()}}, upsert=True)
    log_event("info", "Cart cleared", {"session_id": sid})
    return get_cart(sid)

def add_to_cart(session_id: str, item_id: str, quantity: int = 1) -> Dict[str, Any]:
    sid = (session_id or '').strip() or 'default'
    if quantity <= 0:
        raise HTTPException(400, "quantity musí být > 0")

    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(400, "Neplatné item_id")

    item = col_items().find_one({'_id': oid})
    if not item:
        raise HTTPException(404, "Item nenalezen")

    # dostupnost
    avail = int(item.get("quantity", 0) or 0)
    if avail < quantity:
        raise HTTPException(400, "Nedostatečné množství skladem")

    cart = _cart_col().find_one({'_id': sid}) or {'_id': sid, 'items': [], 'updated': datetime.utcnow()}
    items: List[Dict[str, Any]] = cart.get('items') or []

    # pokud už je v cartu, navýšit
    found = False
    for it in items:
        if it.get('item_id') == str(oid):
            new_q = int(it.get('quantity', 1)) + int(quantity)
            if avail < new_q:
                raise HTTPException(400, "Nedostatečné množství skladem")
            it['quantity'] = new_q
            found = True
            break

    if not found:
        items.append({
            "item_id": str(oid),
            "quantity": int(quantity),
            "vyrobce": item.get("vyrobce"),
            "model": item.get("model"),
            "orig_file_id": item.get("orig_file_id"),
            "price": float(item.get("price", 0) or 0),
        })

    _cart_col().update_one(
        {'_id': sid},
        {'': {'items': items, 'updated': datetime.utcnow()}},
        upsert=True
    )
    log_event("info", "Item added to cart", {"session_id": sid, "item_id": str(oid), "quantity": int(quantity)})
    return get_cart(sid)

def checkout(session_id: str, customer: Optional[Dict[str, Any]] = None, shipping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    sid = (session_id or '').strip() or 'default'
    cart = _cart_col().find_one({'_id': sid})
    if not cart or not cart.get('items'):
        raise HTTPException(400, "Košík je prázdný")

    cart_items = cart.get('items') or []

    # zvaliduj znovu dostupnost + spočti total
    total = 0.0
    order_items = []
    for it in cart_items:
        try:
            oid = ObjectId(it['item_id'])
        except Exception:
            raise HTTPException(400, "Neplatné item_id v košíku")

        db_item = col_items().find_one({'_id': oid})
        if not db_item:
            raise HTTPException(404, f"Item {it['item_id']} nenalezen")

        qty = int(it.get('quantity', 1))
        avail = int(db_item.get('quantity', 0) or 0)
        if avail < qty:
            raise HTTPException(400, f"Nedostatečné množství skladem pro {it['item_id']}")

        price = float(db_item.get('price', it.get('price', 0)) or 0)
        total += qty * price

        order_items.append({
            "item_id": str(oid),
            "quantity": qty,
            "vyrobce": db_item.get("vyrobce"),
            "model": db_item.get("model"),
            "orig_file_id": db_item.get("orig_file_id"),
            "price": price,
        })

    # vytvoř order
    order_doc = {
        "created": datetime.utcnow(),
        "session_id": sid,
        "customer": customer or {},
        "shipping": shipping or {},
        "items": order_items,
        "total": float(total),
        "status": "created",
        "paid": False,
        "paid_at": None,
        "shipped": False,
        "shipped_at": None,
    }
    ins = col_orders().insert_one(order_doc)
    order_id = str(ins.inserted_id)

    # odečti sklad (quantity) + případně status
    for it in order_items:
        oid = ObjectId(it['item_id'])
        qty = int(it['quantity'])
        col_items().update_one(
            {'_id': oid},
            {'': {'quantity': -qty}}
        )

    # vyprázdni cart
    _cart_col().update_one({'_id': sid}, {'': {'items': [], 'updated': datetime.utcnow()}}, upsert=True)

    log_event("info", "Checkout created order", {"session_id": sid, "order_id": order_id, "total": total})
    return {"ok": True, "order_id": order_id, "total": float(total)}
