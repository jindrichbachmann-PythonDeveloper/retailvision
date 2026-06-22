# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse

from app.services.gridfs_service import get_gridfs_file
from app.services.mongo_ctx import col_items
from app.services.auth_service import get_current_user_optional

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


@router.get("/api/image/{file_id}")
def get_image(
    file_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
):
    item = col_items().find_one({"orig_file_id": file_id})

    if not item:
        raise HTTPException(status_code=404, detail="Obrázek nenalezen")

    uid = get_user_uid(user)
    item_uid = item.get("user_id")

    if uid and str(item_uid) == str(uid):
        pass

    elif item.get("approved") is True:
        pass

    else:
        raise HTTPException(status_code=403, detail="Nemáš přístup k obrázku")

    f = get_gridfs_file(file_id)

    ctype = (
        getattr(f, "content_type", None)
        or getattr(f, "contentType", None)
        or "application/octet-stream"
    )

    return StreamingResponse(f, media_type=ctype)