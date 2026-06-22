from fastapi import APIRouter, Query
from app.services.customers_service import seed_customers, list_customers, random_customer

router = APIRouter()

@router.post("/api/customers/seed")
def customers_seed(n: int = Query(20)):
    return seed_customers(n=int(n))

@router.get("/api/customers/list")
def customers_list(limit: int = 200, skip: int = 0):
    return list_customers(limit=limit, skip=skip)

@router.get("/api/customers/random")
def customers_random():
    return random_customer()
