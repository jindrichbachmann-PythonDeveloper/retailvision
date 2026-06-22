from fastapi import APIRouter, HTTPException, Depends, Request
from bson import ObjectId

from app.services.auth_service import get_current_user
from app.services.mongo_ctx import col_items, get_fs

router = APIRouter()


def get_user_id_variants(user) -> list:
    uid = user.get("uid") or user.get("id") or user.get("user_id")

    user_ids = [str(uid)]

    if str(uid).isdigit():
        user_ids.append(int(uid))

    return user_ids


def get_current_domain(request: Request) -> str:
    domain = (request.headers.get("host") or "").split(":")[0].lower()

    if domain in ("127.0.0.1", "localhost"):
        domain = "retailvisionuzivatel.cz"

    return domain


@router.post("/api/items/clear_all")
def items_clear_all(request: Request, user=Depends(get_current_user)):
    user_ids = get_user_id_variants(user)
    domain = get_current_domain(request)
    
    query = {
        "$and": [
            {
                "$or": [
                    {"user_id": {"$in": user_ids}},
                    {"user_id": None},
                    {"user_id": {"$exists": False}},
                ]
            },
            {
                "$or": [
                    {"domain": domain},
                    {"domain": None},
                    {"domain": {"$exists": False}},
                ]
            }
        ]
    }

    items = list(col_items().find(query))

    fs = get_fs()
    deleted_images = 0

    for item in items:
        try:
            fid = (item.get("orig_file_id") or "").strip()

            if fid:
                fs.delete(ObjectId(fid))
                deleted_images += 1

        except Exception:
            pass

    res = col_items().delete_many(query)

    print("🧹 CLEAR ALL DEBUG")
    print("USER:", user)
    print("USER_IDS:", user_ids)
    print("DOMAIN:", domain)
    print("QUERY:", query)
    print("FOUND ITEMS:", len(items))
    print("DELETED ITEMS:", int(res.deleted_count))
    print("DELETED IMAGES:", deleted_images)

    return {
        "ok": True,
        "domain": domain,
        "deleted_items": int(res.deleted_count),
        "deleted_images": deleted_images,
    }


@router.delete("/api/item/{item_id}")
def item_delete(item_id: str, request: Request, user=Depends(get_current_user)):
    user_ids = get_user_id_variants(user)
    domain = get_current_domain(request)

    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Neplatné item_id")

    query = {
        "_id": oid,
        "$and": [
            {
                "$or": [
                    {"user_id": {"$in": user_ids}},
                    {"user_id": None},
                    {"user_id": {"$exists": False}},
                ]
            },
            {
                "$or": [
                    {"domain": domain},
                    {"domain": None},
                    {"domain": {"$exists": False}},
                ]
            }
        ]
    }
    
    item = col_items().find_one(query)

    if not item:
        raise HTTPException(status_code=404, detail="Item nenalezen nebo nepatří této doméně")

    col_items().delete_one(query)

    try:
        fid = (item.get("orig_file_id") or "").strip()

        if fid:
            fs = get_fs()
            fs.delete(ObjectId(fid))

    except Exception:
        pass

    return {
        "ok": True,
        "domain": domain,
        "deleted_id": item_id,
    }