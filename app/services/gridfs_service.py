# -*- coding: utf-8 -*-
from typing import Optional
from bson import ObjectId
from fastapi import HTTPException

import gridfs
from pymongo.database import Database

from app.services.mongo_ctx import get_db

def _fs():
    db: Database = get_db()
    return gridfs.GridFS(db)

def save_image_bytes_to_gridfs(raw: bytes, filename: str = "image.jpg", content_type: str = "image/jpeg") -> ObjectId:
    if not raw:
        raise HTTPException(status_code=400, detail="empty bytes")
    fs = _fs()
    fid = fs.put(raw, filename=filename, contentType=content_type)
    return fid

def get_gridfs_file(file_id: str):
    try:
        oid = ObjectId(file_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Neplatné file_id")

    fs = _fs()
    try:
        f = fs.get(oid)
        return f
    except Exception:
        raise HTTPException(status_code=404, detail="Soubor nenalezen v GridFS")

def delete_gridfs_file(file_id: str) -> bool:
    try:
        oid = ObjectId(file_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Neplatné file_id")

    fs = _fs()
    try:
        fs.delete(oid)
        return True
    except Exception:
        return False
