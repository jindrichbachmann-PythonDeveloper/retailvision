import os
from pymongo import MongoClient
import gridfs

_MONGO = None
_FS = None

def get_mongo():
    global _MONGO
    if _MONGO is not None:
        return _MONGO

    uri = os.getenv("MONGO_URI", "").strip()
    dbname = os.getenv("MONGO_DB", "").strip()
    if not uri or not dbname:
        raise RuntimeError("Chybí MONGO_URI nebo MONGO_DB v .env")

    client = MongoClient(uri)
    _MONGO = client[dbname]
    return _MONGO

def get_fs():
    global _FS
    if _FS is not None:
        return _FS

    db = get_mongo()
    bucket = os.getenv("MONGO_GRIDFS_BUCKET", "fs").strip() or "fs"
    _FS = gridfs.GridFS(db, collection=bucket)
    return _FS
