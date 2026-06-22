from fastapi import APIRouter
from app.services.mongo_ctx import col_items, col_orders, col_logs, get_db

router = APIRouter()

@router.get("/api/status/")
def status():
    db = get_db()
    invoices_col = db['invoices'] if 'invoices' in db.list_collection_names() else None

    data = {
        'ok': True,
        'mongo': {
            'hodinky': int(col_items().count_documents({})),
            'orders': int(col_orders().count_documents({})),
            'event_logs': int(col_logs().count_documents({})),
            'invoices': int(invoices_col.count_documents({})) if invoices_col else 0,
        }
    }
    return data
