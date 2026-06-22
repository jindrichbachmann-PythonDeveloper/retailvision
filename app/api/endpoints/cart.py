# -*- coding: utf-8 -*-
import os
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import smtplib
from email.mime.text import MIMEText
import secrets

import stripe

from app.services.pg_service import pg_fetchone, pg_exec

router = APIRouter()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

def get_or_create_customer(user_id: int, customer: dict) -> int:
    email = (customer.get("email") or "").strip().lower()

    if not email:
        raise HTTPException(status_code=400, detail="Chybí e-mail zákazníka")

    data = {
        "user_id": user_id,
        "email": email,
        "first_name": customer.get("first_name"),
        "last_name": customer.get("last_name"),
        "phone": customer.get("phone"),
        "street": customer.get("street"),
        "city": customer.get("city"),
        "postcode": customer.get("postcode"),
        "country": customer.get("country"),
    }

    row = pg_fetchone(
        """
        SELECT id
        FROM customers
        WHERE user_id = :user_id
          AND lower(email) = lower(:email)
        LIMIT 1
        """,
        data
    )

    if row:
        customer_id = int(row["id"])

        pg_exec(
            """
            UPDATE customers
            SET
                first_name = :first_name,
                last_name = :last_name,
                phone = :phone,
                street = :street,
                city = :city,
                postcode = :postcode,
                country = :country,
                updated_at = now()
            WHERE id = :customer_id
              AND user_id = :user_id
            """,
            {
                **data,
                "customer_id": customer_id,
            }
        )

        print("👤 Zákazník nalezen a aktualizován:", customer_id)
        return customer_id

    pg_exec(
        """
        INSERT INTO customers (
            user_id,
            email,
            first_name,
            last_name,
            phone,
            street,
            city,
            postcode,
            country,
            email_verified
        )
        VALUES (
            :user_id,
            :email,
            :first_name,
            :last_name,
            :phone,
            :street,
            :city,
            :postcode,
            :country,
            FALSE
        )
        """,
        data
    )

    row = pg_fetchone(
        """
        SELECT id
        FROM customers
        WHERE user_id = :user_id
          AND lower(email) = lower(:email)
        LIMIT 1
        """,
        data
    )

    if not row:
        raise HTTPException(status_code=500, detail="Zákazník nebyl vytvořen")

    customer_id = int(row["id"])
    print("👤 Nový zákazník vytvořen:", customer_id)
    return customer_id

def get_owner_user_id(request: Request) -> int:
    host = (request.headers.get("host") or "").split(":")[0].lower()

    if host in ("127.0.0.1", "localhost"):
        host = "retailvisionuzivatel.cz"

    row = pg_fetchone(
        """
        SELECT user_id
        FROM domains
        WHERE domain = :domain
          AND is_active = TRUE
        LIMIT 1
        """,
        {"domain": host}
    )

    if not row:
        raise HTTPException(
            status_code=400,
            detail=f"Doména není registrovaná: {host}"
        )

    return int(row["user_id"])

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CartItem(BaseModel):
    item_id: str
    name: Optional[str] = None
    price: Optional[float] = None
    quantity: int = 1


class CartResponse(BaseModel):
    items: List[CartItem] = Field(default_factory=list)


CARTS: Dict[str, List[CartItem]] = {}


def get_cart_for_session(session_id: str) -> List[CartItem]:
    sid = (session_id or "").strip() or "default"
    cart = CARTS.get(sid)
    if cart is None:
        cart = []
        CARTS[sid] = cart
    return cart


def find_cart_item(cart: List[CartItem], item_id: str) -> Optional[CartItem]:
    for it in cart:
        if it.item_id == item_id:
            return it
    return None


class AddToCartRequest(BaseModel):
    item_id: str
    quantity: int = 1


class CustomerInfo(BaseModel):
    first_name: str
    last_name: str
    street: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = "Česká republika"
    email: Optional[str] = None
    phone: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    bank_account: Optional[str] = None


class CheckoutRequest(BaseModel):
    shipping_method: str = "ceska_posta"
    payment_method: str = "card"
    customer: CustomerInfo

SHIPPING_PRICES = {
    "personal_pickup": {"name": "Osobní odběr na prodejně", "amount": 0},
    "zasilkovna": {"name": "Doprava – Zásilkovna", "amount": 7900},
    "ppl": {"name": "Doprava – PPL", "amount": 10900},
    "dpd": {"name": "Doprava – DPD", "amount": 11900},
    "ceska_posta": {"name": "Doprava – Česká pošta", "amount": 9900},
}

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")


class EmailVerificationRequest(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@router.post("/api/cart/send-email-verification", response_class=JSONResponse)
def send_email_verification(request: Request, body: EmailVerificationRequest):
    email = (body.email or "").strip().lower()

    if not email:
        raise HTTPException(status_code=400, detail="E-mail je povinný")

    domain = (request.headers.get("host") or "").split(":")[0].lower()
    if domain in ("127.0.0.1", "localhost"):
        domain = "retailvisionuzivatel.cz"

    row = pg_fetchone(
        """
        SELECT verified
        FROM email_verifications
        WHERE email = :email
        LIMIT 1
        """,
        {"email": email}
    )

    if row and row.get("verified"):
        return {
            "ok": True,
            "already_verified": True,
            "message": "E-mail už je ověřený.",
        }

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)

    pg_exec(
        """
        INSERT INTO email_verifications
            (email, token, verified, expires_at, created_at)
        VALUES
            (:email, :token, FALSE, :expires, now())
        ON CONFLICT (email)
        DO UPDATE SET
            token = EXCLUDED.token,
            verified = FALSE,
            expires_at = EXCLUDED.expires_at,
            created_at = now(),
            verified_at = NULL
        """,
        {
            "email": email,
            "token": token,
            "expires": expires,
        }
    )

    verify_url = f"https://{domain}/api/cart/verify-email?token={token}"

    if not (SMTP_HOST and SMTP_FROM):
        raise HTTPException(status_code=500, detail="SMTP není nakonfigurováno")

    msg = MIMEText(
        f"""Dobrý den,

pro dokončení objednávky prosím ověřte svůj e-mail kliknutím na odkaz:

{verify_url}

Odkaz je platný 30 minut.

S pozdravem,
{domain}
""",
        "plain",
        "utf-8",
    )

    msg["Subject"] = "Ověření e-mailu pro objednávku"
    msg["From"] = SMTP_FROM
    msg["To"] = email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.ehlo()
        if SMTP_USER and SMTP_PASS:
            s.starttls()
            s.ehlo()
            s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_FROM, [email], msg.as_string())

    print("📧 Ověřovací e-mail odeslán:", email)

    return {
        "ok": True,
        "message": "Ověřovací e-mail byl odeslán.",
    }

@router.get("/api/cart/verify-email", response_class=JSONResponse)
def verify_email(token: str):
    token = (token or "").strip()

    if not token:
        raise HTTPException(status_code=400, detail="Token je povinný")

    row = pg_fetchone(
        """
        SELECT
            email,
            expires_at,
            verified
        FROM email_verifications
        WHERE token = :token
        LIMIT 1
        """,
        {"token": token}
    )

    if not row:
        raise HTTPException(status_code=400, detail="Neplatný ověřovací token")

    expires = row.get("expires_at")
    now = datetime.now(timezone.utc)

    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if expires and expires < now:
        raise HTTPException(status_code=400, detail="Ověřovací odkaz vypršel")

    pg_exec(
        """
        UPDATE email_verifications
        SET
            verified = TRUE,
            verified_at = now()
        WHERE token = :token
        """,
        {"token": token}
    )

    print("✅ E-mail ověřen:", row["email"])

    return {
        "ok": True,
        "message": "E-mail byl úspěšně ověřen.",
        "email": row["email"],
    }

@router.get("/api/cart/check-email-verified", response_class=JSONResponse)
def check_email_verified(email: str):
    email = (email or "").strip().lower()

    if not email:
        raise HTTPException(status_code=400, detail="E-mail je povinný")

    row = pg_fetchone(
        """
        SELECT verified
        FROM email_verifications
        WHERE lower(email) = lower(:email)
        LIMIT 1
        """,
        {"email": email}
    )

    return {
        "ok": True,
        "verified": bool(row and row.get("verified")),
    }

@router.get("/api/cart", response_model=CartResponse)
def get_cart(x_session_id: Optional[str] = Header(None)):
    cart = get_cart_for_session(x_session_id)
    return CartResponse(items=cart)

@router.post("/api/cart/add", response_class=JSONResponse)
def add_to_cart(body: AddToCartRequest, x_session_id: Optional[str] = Header(None)):
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity musí být >= 1")

    cart = get_cart_for_session(x_session_id)
    
    row = pg_fetchone(
        """
        SELECT
            name,
            price_cents,
            is_ready_for_sale
        FROM products
        WHERE mongo_item_id = :item_id
        LIMIT 1
        """,
        {
            "item_id": body.item_id,
        }
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Produkt nebyl nalezen"
        )

    if not row.get("is_ready_for_sale"):
        raise HTTPException(
            status_code=400,
            detail="Produkt není připraven k prodeji"
        )

    price_cents = int(row.get("price_cents") or 0)

    if price_cents <= 0:
        raise HTTPException(
            status_code=400,
            detail="Produkt nemá platnou cenu"
        )

    name = row.get("name") or f"Položka {body.item_id}"
    price = price_cents / 100

    existing = find_cart_item(cart, body.item_id)
    if existing:
        existing.quantity += body.quantity
    else:
        cart.append(CartItem(
            item_id=body.item_id,
            name=name,
            price=price,
            quantity=body.quantity
        ))

    return {"ok": True, "message": "Přidáno do košíku", "items_count": len(cart)}


@router.post("/api/cart/clear", response_class=JSONResponse)
def clear_cart(x_session_id: Optional[str] = Header(None)):
    cart = get_cart_for_session(x_session_id)
    cart.clear()
    return {"ok": True, "message": "Košík vyprázdněn"}

@router.post("/api/cart/checkout", response_class=JSONResponse)
def checkout_cart(request: Request, body: CheckoutRequest, x_session_id: Optional[str] = Header(None)):
    cart = get_cart_for_session(x_session_id)

    print(">>> /api/cart/checkout invoked")
    print(f">>> payment_method={body.payment_method}, shipping_method={body.shipping_method}")

    if not cart:
        raise HTTPException(status_code=400, detail="Košík je prázdný")

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe není nakonfigurován")

    if body.payment_method != "card":
        raise HTTPException(
            status_code=400,
            detail="Zatím podporujeme jen platbu kartou přes Stripe"
        )

    customer = body.customer.model_dump()

    customer_email = (customer.get("email") or "").strip()

    if not customer_email:
        raise HTTPException(
            status_code=400,
            detail="Chybí e-mail zákazníka"
        )
    
    is_pickup = body.shipping_method == "personal_pickup"

    if not customer.get("first_name") or not customer.get("last_name"):
        raise HTTPException(
            status_code=400,
            detail="Chybí jméno nebo příjmení zákazníka"
        )

    if not is_pickup and (
        not customer.get("street")
        or not customer.get("city")
        or not customer.get("postcode")
    ):
        raise HTTPException(
            status_code=400,
            detail="Chybí doručovací adresa"
        )
    
    user_id = get_owner_user_id(request)

    domain = (request.headers.get("host") or "").split(":")[0].lower()

    if domain in ("127.0.0.1", "localhost"):
        domain = "retailvisionuzivatel.cz"

    print("🌐 DOMAIN:", domain)
    print("🏪 OWNER user_id:", user_id)
    print("📧 CUSTOMER EMAIL:", customer_email)

    customer_id = get_or_create_customer(user_id, customer)

    print("👤 CUSTOMER ID:", customer_id)

    verification = pg_fetchone(
        """
        SELECT verified
        FROM email_verifications
        WHERE lower(email) = lower(:email)
        LIMIT 1
        """,
        {
            "email": customer_email,
        }
    )

    if not verification or not verification.get("verified"):
        raise HTTPException(
            status_code=403,
            detail="E-mail zákazníka není ověřen"
        )
    
    total_cents = 0
    line_items = []
    order_items = []

    for it in cart:
        qty = int(it.quantity or 1)

        price_cents = int(round(float(it.price or 1.0) * 100))

        if price_cents <= 0:
            price_cents = 100

        item_name = it.name or f"Položka {it.item_id}"

        order_items.append({
            "item_id": it.item_id,
            "name": item_name,
            "quantity": qty,
            "price_cents": price_cents,
        })

        line_items.append({
            "price_data": {
                "currency": "czk",
                "product_data": {
                    "name": item_name
                },
                "unit_amount": price_cents,
            },
            "quantity": qty,
        })

        total_cents += price_cents * qty


    shipping_cfg = SHIPPING_PRICES.get(body.shipping_method)
    shipping_price_cents = 0

    if shipping_cfg:
        shipping_price_cents = int(shipping_cfg["amount"])

        if shipping_price_cents > 0:
            line_items.append({
                "price_data": {
                    "currency": "czk",
                    "product_data": {"name": shipping_cfg["name"]},
                    "unit_amount": shipping_price_cents,
                },
                "quantity": 1,
            })

        total_cents += shipping_price_cents

    pg_exec(
        """
        INSERT INTO orders (
            user_id,
            customer_id,
            customer_email,
            domain,
            customer_first_name,
            customer_last_name,
            customer_street,
            customer_city,
            customer_postcode,
            customer_country,
            customer_phone,
            customer_bank_account,
            status,
            total_cents,
            currency,
            shipping_method,
            shipping_price_cents,
            shipped
        )
        VALUES (
            :user_id,
            :customer_id,
            :customer_email,
            :domain,
            :customer_first_name,
            :customer_last_name,
            :customer_street,
            :customer_city,
            :customer_postcode,
            :customer_country,
            :customer_phone,
            :customer_bank_account,
            'pending',
            :total_cents,
            'czk',
            :shipping_method,
            :shipping_price_cents,
            FALSE
        )
        """,
        {
            "user_id": user_id,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "domain": domain,
            "customer_first_name": customer.get("first_name"),
            "customer_last_name": customer.get("last_name"),
            "customer_street": customer.get("street"),
            "customer_city": customer.get("city"),
            "customer_postcode": customer.get("postcode"),
            "customer_country": customer.get("country"),
            "customer_phone": customer.get("phone"),
            "customer_bank_account": customer.get("bank_account"),
            "total_cents": total_cents,
            "shipping_method": body.shipping_method,
            "shipping_price_cents": shipping_price_cents,
        }
    )

    order = pg_fetchone(
        """
        SELECT id
        FROM orders
        WHERE user_id = :user_id
        ORDER BY id DESC
        LIMIT 1
        """,
        {"user_id": user_id}
    )

    if not order:
        raise HTTPException(status_code=500, detail="Objednávka nebyla vytvořena")

    order_id = int(order["id"])
    print("🧾 Objednávka vytvořena v PostgreSQL:", order_id)

    for it in order_items:
        pg_exec(
            """
            INSERT INTO order_items (
                user_id,
                order_id,
                product_id,
                name,
                price_cents,
                quantity,
                image_id
            )
            VALUES (
                :user_id,
                :order_id,
                NULL,
                :name,
                :price_cents,
                :quantity,
                NULL
            )
            """,
            {
                "user_id": user_id,
                "order_id": order_id,
                "name": it["name"],
                "price_cents": it["price_cents"],
                "quantity": it["quantity"],
            }
        )

    try:
        base_url = str(request.base_url).rstrip("/")
        success_url = f"{base_url}/?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/?payment=cancel"

        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=line_items,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=customer_email,
            metadata={
                "order_id": str(order_id),
                "user_id": str(user_id),
            },
        )

        pg_exec(
            """
            UPDATE orders
            SET stripe_session_id = :stripe_session_id
            WHERE id = :order_id
              AND user_id = :user_id
            """,
            {
                "stripe_session_id": session.id,
                "order_id": order_id,
                "user_id": user_id,
            }
        )

        print("✅ Stripe session vytvořena:", session.id)

    except Exception as e:
        print("❌ Stripe chyba:", e)
        raise HTTPException(status_code=500, detail="Chyba při vytváření Stripe platby")

    cart.clear()

    return {
        "ok": True,
        "message": "Objednávka vytvořena – čekám na platbu",
        "stripe_session_id": session.id,
        "checkout_url": session.url,
        "order_id": order_id,
        "total_cents": total_cents,
        "total": total_cents / 100,
        "shipping_method": body.shipping_method,
        "payment_method": body.payment_method,
    }