import random
import string
from typing import Dict, Any, List

from fastapi import HTTPException

from app.services.mongo_ctx import get_db

def _col():
    return get_db()['customers']

FIRST = ['Jan', 'Petr', 'Tomáš', 'Lucie', 'Tereza', 'Eva', 'Martin', 'David', 'Jana', 'Kateřina']
LAST  = ['Novák', 'Svoboda', 'Dvořák', 'Černý', 'Procházka', 'Kučera', 'Veselý', 'Horák', 'Němec', 'Pokorná']
STREETS = ['Hlavní', 'Nádražní', 'Školní', 'Smetanova', 'Komenského', 'Jiráskova', 'Husova', 'Palackého']

def _rand_phone() -> str:
    return "+420 " + "".join(random.choice(string.digits) for _ in range(3)) + " " + "".join(random.choice(string.digits) for _ in range(3)) + " " + "".join(random.choice(string.digits) for _ in range(3))

def _rand_email(first: str, last: str) -> str:
    base = f"{first}.{last}".lower()
    base = base.replace('á','a').replace('č','c').replace('ď','d').replace('é','e').replace('ě','e').replace('í','i').replace('ň','n').replace('ó','o').replace('ř','r').replace('š','s').replace('ť','t').replace('ú','u').replace('ů','u').replace('ý','y').replace('ž','z')
    return f"{base}{random.randint(1,999)}@example.com"

def seed_customers(n: int = 20) -> Dict[str, Any]:
    if n <= 0:
        raise HTTPException(400, "n musí být > 0")

    inserted = 0
    created = []

    for _ in range(int(n)):
        first = random.choice(FIRST)
        last = random.choice(LAST)
        name = f"{first} {last}"
        email = _rand_email(first, last)
        phone = _rand_phone()
        addr = f"{random.choice(STREETS)} {random.randint(1,200)}, Praha"

        doc = {
            "name": name,
            "email": email,
            "phone": phone,
            "address": addr,
            "created": __import__("datetime").datetime.utcnow(),
        }
        res = _col().insert_one(doc)
        doc["_id"] = str(res.inserted_id)
        created.append(doc)
        inserted += 1

    return {"ok": True, "inserted": inserted, "customers": created}

def list_customers(limit: int = 200, skip: int = 0) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    skip = max(0, int(skip))

    cur = _col().find({}).skip(skip).limit(limit).sort("_id", -1)
    out = []
    for d in cur:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out

def random_customer() -> Dict[str, Any]:
    # Mongo random přes 
    res = list(_col().aggregate([{"": {"size": 1}}]))
    if not res:
        raise HTTPException(404, "Žádní zákazníci v DB")
    d = res[0]
    d["_id"] = str(d["_id"])
    return d
