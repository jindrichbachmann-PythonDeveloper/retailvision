# -*- coding: utf-8 -*-
import os
import stripe

from fastapi import APIRouter, Request, HTTPException, Body
from fastapi.responses import JSONResponse

from app.services.pg_service import pg_fetchone, pg_exec
from app.services.invoice_csv_service import generate_invoice_pg

router = APIRouter()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


@router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET není nastaven")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        print("❌ Stripe webhook signature chyba:", e)
        raise HTTPException(status_code=400, detail="Neplatný Stripe webhook")

    event_type = event.get("type")
    print("✅ Stripe webhook event:", event_type)

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]

        stripe_session_id = session.get("id")
        payment_intent_id = session.get("payment_intent")
        amount_total = session.get("amount_total")
        currency = session.get("currency", "czk")

        if not stripe_session_id:
            return {"ok": True, "ignored": "missing_session_id"}

        order = pg_fetchone(
            """
            SELECT *
            FROM orders
            WHERE stripe_session_id = :stripe_session_id
            LIMIT 1
            """,
            {"stripe_session_id": stripe_session_id}
        )

        if not order:
            print("⚠️ Objednávka pro Stripe session zatím není v PostgreSQL:", stripe_session_id)
            return {
                "ok": True,
                "warning": "order_not_found_in_postgres",
                "stripe_session_id": stripe_session_id,
            }

        if order.get("status") == "paid" or order.get("paid_at"):
            return {
                "ok": True,
                "already_paid": True,
                "order_id": order["id"],
            }

        pg_exec(
            """
            UPDATE orders
            SET
                status = 'paid',
                paid_at = now(),
                stripe_payment_intent_id = :payment_intent_id,
                total_cents = COALESCE(:amount_total, total_cents),
                currency = COALESCE(:currency, currency)
            WHERE id = :order_id
              AND user_id = :user_id
            """,
            {
                "order_id": order["id"],
                "user_id": order["user_id"],
                "payment_intent_id": payment_intent_id,
                "amount_total": amount_total,
                "currency": currency,
            }
        )

        print("💰 Objednávka označena jako zaplacená:", order["id"])

        return {
            "ok": True,
            "paid": True,
            "order_id": order["id"],
            "stripe_session_id": stripe_session_id,
        }

    return {"ok": True, "ignored": event_type}


@router.post("/api/stripe/checkout_success", response_class=JSONResponse)
def stripe_checkout_success(data: dict = Body(...)):
    """
    Webhook potvrzuje platbu.
    Tady po návratu ze Stripe dokončíme fakturu nad PostgreSQL objednávkou.
    """
    session_id = (data.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id je povinný")

    order = pg_fetchone(
        """
        SELECT *
        FROM orders
        WHERE stripe_session_id = :stripe_session_id
        LIMIT 1
        """,
        {"stripe_session_id": session_id}
    )

    if not order:
        return {
            "ok": True,
            "message": "Platba možná proběhla, ale objednávka ještě není v PostgreSQL",
            "stripe_session_id": session_id,
            "invoice_created": False,
            "email_sent": False,
        }

    customer_email = (order.get("customer_email") or "").strip()

    print("🧾 CHECKOUT SUCCESS ORDER:", order["id"])
    print("📧 EMAIL ZÁKAZNÍKA Z POSTGRES:", customer_email)
    print("💰 STATUS OBJEDNÁVKY:", order.get("status"))

    if order.get("status") != "paid":
        return {
            "ok": True,
            "order_id": order["id"],
            "status": order.get("status"),
            "paid_at": str(order["paid_at"]) if order.get("paid_at") else None,
            "customer_email": customer_email,
            "email_ready": bool(customer_email),
            "invoice_created": False,
            "email_sent": False,
            "message": "Objednávka ještě není označená jako paid webhookem.",
        }

    if order.get("invoice_number"):
        return {
            "ok": True,
            "order_id": order["id"],
            "status": order.get("status"),
            "paid_at": str(order["paid_at"]) if order.get("paid_at") else None,
            "customer_email": customer_email,
            "email_ready": bool(customer_email),
            "invoice_created": True,
            "invoice_number": order.get("invoice_number"),
            "email_sent": False,
            "already_invoiced": True,
        }

    try:
        invoice = generate_invoice_pg(int(order["id"]))
        print("🧾 PG faktura:", invoice)
    except Exception as e:
        print("❌ Chyba při generování PG faktury:", repr(e))
        raise HTTPException(status_code=500, detail=f"Chyba při generování faktury: {e}")

    return {
        "ok": True,
        "order_id": order["id"],
        "status": order.get("status"),
        "paid_at": str(order["paid_at"]) if order.get("paid_at") else None,
        "customer_email": customer_email,
        "email_ready": bool(customer_email),
        "invoice_created": bool(invoice.get("ok")),
        "invoice_number": invoice.get("invoice_number"),
        "email_sent": bool(invoice.get("email_sent")),
        "csv_path": invoice.get("csv_path"),
    }