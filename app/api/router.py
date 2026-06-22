from fastapi import APIRouter

# --- CORE ---
from app.api.endpoints.health import router as health_router
from app.api.endpoints.status import router as status_router
from app.api.endpoints.pg import router as pg_router

# --- ANALYZE / PREVIEW ---
from app.api.endpoints.analyze import router as analyze_router
from app.api.endpoints.detect_preview import router as preview_router

# --- INVENTORY ---
from app.api.endpoints.list import router as list_router
from app.api.endpoints.items import router as items_router
from app.api.endpoints.products import router as products_router
from app.api.endpoints.image import router as image_router
from app.api.endpoints.images import router as images_router

# --- ORDERS / CART / STRIPE ---
from app.api.endpoints.orders import router as orders_router
from app.api.endpoints.cart import router as cart_router
from app.api.endpoints.stripe import router as stripe_router

# --- INVOICES ---
from app.api.endpoints.invoices import router as invoices_router

# --- USERS / AUTH ---
from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.users import router as users_router

# --- CUSTOMERS ---
from app.api.endpoints.customers import router as customers_router

# --- LOGS ---
from app.api.endpoints.logs import router as logs_router

# --- TEST / WEB ---
from app.api.endpoints.test_upload import router as test_upload_router
from app.api.endpoints.web import router as web_router

# --- DEBUG ---
from app.api.endpoints.whoami import router as whoami_router


api_router = APIRouter()

# CORE
api_router.include_router(health_router, tags=["health"])
api_router.include_router(status_router, tags=["status"])
api_router.include_router(pg_router, tags=["pg"])

# ANALYZE / PREVIEW
api_router.include_router(analyze_router, tags=["analyze"])
api_router.include_router(preview_router, tags=["preview"])

# INVENTORY
api_router.include_router(list_router, tags=["list"])
api_router.include_router(items_router, tags=["items"])
api_router.include_router(products_router, tags=["products"])
api_router.include_router(image_router, tags=["image"])
api_router.include_router(images_router, tags=["images"])

# ORDERS / CART / STRIPE
api_router.include_router(orders_router, tags=["orders"])
api_router.include_router(cart_router, tags=["cart"])
api_router.include_router(stripe_router, tags=["stripe"])

# INVOICES
api_router.include_router(invoices_router, tags=["invoices"])

# USERS / AUTH
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(users_router, tags=["users"])

# CUSTOMERS
api_router.include_router(customers_router, tags=["customers"])

# LOGS
api_router.include_router(logs_router, tags=["logs"])

# TEST / WEB
api_router.include_router(test_upload_router, tags=["test_upload"])
api_router.include_router(web_router, tags=["web"])

# DEBUG
api_router.include_router(whoami_router, tags=["debug"])