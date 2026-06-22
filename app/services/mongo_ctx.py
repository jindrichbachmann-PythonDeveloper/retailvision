import os
from pymongo import MongoClient
from gridfs import GridFS

# 1:1 názvy z monolitu
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME   = os.getenv("DB_NAME", "hodinkovy_obchod")

_client = None
_db = None
_fs = None

_col_items = None
_col_orders = None
_col_logs = None
_col_odebirky = None

def get_mongo_client():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client

def get_db():
    global _db
    if _db is None:
        _db = get_mongo_client()[DB_NAME]
    return _db

def get_fs():
    global _fs
    if _fs is None:
        _fs = GridFS(get_db())
    return _fs

def col_items():
    global _col_items
    if _col_items is None:
        _col_items = get_db()["hodinky"]
    return _col_items

def col_orders():
    global _col_orders
    if _col_orders is None:
        _col_orders = get_db()["orders"]
    return _col_orders

def col_logs():
    global _col_logs
    if _col_logs is None:
        _col_logs = get_db()["event_logs"]
    return _col_logs

def col_odebirky():
    global _col_odebirky
    if _col_odebirky is None:
        _col_odebirky = get_db()["seznam_odebirek"]
    return _col_odebirky
