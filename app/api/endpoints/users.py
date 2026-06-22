# -*- coding: utf-8 -*-
from fastapi import APIRouter, Query

from app.services.users_service import seed_users, list_users, random_user

router = APIRouter()

# --- USERS seed/list/random (Postgres) ---
@router.post("/api/users/seed")
def users_seed(n: int = Query(10), default_password: str = Query("test1234")):
    # v monolitu to často bývá admin-only; když chceš, přepnu to později na admin-only
    return seed_users(n=int(n), default_password=default_password)


@router.get("/api/users/list")
def users_list(limit: int = 200, skip: int = 0):
    return list_users(limit=limit, skip=skip)


@router.get("/api/users/random")
def users_random():
    return random_user()