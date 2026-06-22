from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.gridfs_service import save_image_bytes_to_gridfs

router = APIRouter()

@router.post("/api/test_upload/")
async def test_upload(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    fid = save_image_bytes_to_gridfs(raw, file.filename or "upload.bin")
    return {
        "ok": True,
        "file_id": str(fid),
        "filename": file.filename,
        "size": len(raw),
    }
