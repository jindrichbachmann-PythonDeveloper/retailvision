# -*- coding: utf-8 -*-
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from app.services.gridfs_service import save_image_bytes_to_gridfs
from app.services.mongo_ctx import get_db, col_items
from app.services.gridfs_service import _fs

router = APIRouter()

@router.post("/api/images/upload", response_class=JSONResponse)
async def upload_image(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    ctype = (file.content_type or "application/octet-stream")
    fid = save_image_bytes_to_gridfs(raw, filename=file.filename or "upload.bin", content_type=ctype)

    return {
        "ok": True,
        "file_id": str(fid),
        "filename": file.filename,
        "content_type": ctype,
        "size": len(raw),
    }

@router.post("/api/images/clear_all", response_class=JSONResponse)
def clear_all_images():
    print(">>> clear_all_images invoked")

    db = get_db()
    fs = _fs()
    items = col_items()

    try:
        total_files_before = db["fs.files"].count_documents({})
    except Exception:
        total_files_before = None
    print(f"GridFS files before delete: {total_files_before}")

    try:
        total_items_before = items.count_documents({})
    except Exception:
        total_items_before = None
    print(f"Items before delete: {total_items_before}")

    deleted_files = 0
    for file_doc in fs.find({}):
        try:
            fs.delete(file_doc._id)
            deleted_files += 1
        except Exception as e:
            print(f"GridFS delete failed for {file_doc._id}: {e}")

    deleted_items = items.delete_many({}).deleted_count

    print(f"Deleted GridFS files: {deleted_files}")
    print(f"Deleted items: {deleted_items}")

    return {
        "ok": True,
        "message": f"Smazáno souborů: {deleted_files}, položek: {deleted_items}",
        "deleted_files": deleted_files,
        "deleted_items": deleted_items,
        "files_before": total_files_before,
        "items_before": total_items_before,
    }