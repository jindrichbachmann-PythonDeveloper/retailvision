# -*- coding: utf-8 -*-
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query

from app.services.mongo_ctx import col_items
from app.services.auth_service import get_current_user_optional
from app.services.pg_service import pg_fetchall

router = APIRouter()


def get_user_uid(user):
    if not user:
        return None

    return (
        user.get("uid")
        or user.get("id")
        or user.get("user_id")
        or user.get("token_payload", {}).get("uid")
        or user.get("token_payload", {}).get("user_id")
    )


def get_user_id_variants(user) -> list:
    uid = get_user_uid(user)

    if uid is None:
        return []

    user_ids = [str(uid)]

    if str(uid).isdigit():
        user_ids.append(int(uid))

    return user_ids


def get_current_domain(request: Request) -> str:
    domain = (request.headers.get("host") or "").split(":")[0].lower()

    if domain in ("127.0.0.1", "localhost"):
        domain = "retailvisionuzivatel.cz"

    return domain


def domain_filter(domain: str) -> dict:
    return {
        "$or": [
            {"domain": domain},
            {"domain": {"$exists": False}},
        ]
    }


@router.get("/api/list/")
def list_items(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    approved: Optional[int] = None,
    user=Depends(get_current_user_optional),
):
    domain = get_current_domain(request)

    if not user:
        query = {
            "approved": True,
            **domain_filter(domain),
        }

    else:
        user_ids = get_user_id_variants(user)

        if approved == 1:
            query = {
                "$and": [
                    domain_filter(domain),
                    {"approved": True},
                ]
            }

        elif approved == 0:
            query = {
                "$and": [
                    domain_filter(domain),
                    {
                        "user_id": {"$in": user_ids},
                        "approved": False,
                    },
                ]
            }

        else:
            query = {
                "$and": [
                    domain_filter(domain),
                    {
                        "$or": [
                            {"approved": True},
                            {"user_id": {"$in": user_ids}},
                        ]
                    },
                ]
            }

    items = list(
        col_items()
        .find(query)
        .skip(skip)
        .limit(limit)
        .sort("_id", 1)
    )

    mongo_ids = [str(it["_id"]) for it in items]
    product_map = {}

    if mongo_ids:
        rows = pg_fetchall(
            """
            SELECT
                mongo_item_id,
                name,
                description,
                price_cents,
                price_confidence,
                details_confidence,
                manually_edited,
                is_ready_for_sale
            FROM products
            WHERE mongo_item_id IN :mongo_ids
            """,
            {
                "mongo_ids": tuple(mongo_ids),
            }
        )

        product_map = {
            str(row["mongo_item_id"]): row
            for row in rows
        }

    if not user:
        items = [
            it for it in items
            if product_map.get(str(it["_id"]))
            and product_map.get(str(it["_id"])).get("is_ready_for_sale")
        ]

    uid = get_user_uid(user)

    for it in items:
        it["_id"] = str(it["_id"])
        it["is_owner"] = bool(uid and str(it.get("user_id")) == str(uid))

        product = product_map.get(str(it["_id"]))

        if product:
            it["product_name"] = product.get("name")
            it["description"] = product.get("description") or ""
            it["price_cents"] = product.get("price_cents") or 0
            it["price_confidence"] = product.get("price_confidence") or 0
            it["details_confidence"] = product.get("details_confidence") or 0
            it["manually_edited"] = bool(product.get("manually_edited"))
            it["is_ready_for_sale"] = bool(product.get("is_ready_for_sale"))
        else:
            it["description"] = ""
            it["price_cents"] = 0
            it["price_confidence"] = 0
            it["details_confidence"] = 0
            it["manually_edited"] = False
            it["is_ready_for_sale"] = False

    print("📦 LIST DEBUG")
    for it in items[:10]:
        print({
            "_id": it.get("_id"),
            "user_id": it.get("user_id"),
            "domain": it.get("domain"),
            "approved": it.get("approved"),
            "is_ready_for_sale": it.get("is_ready_for_sale"),
        })

    return items