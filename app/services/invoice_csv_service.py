# -*- coding: utf-8 -*-
import os
import csv
import smtplib
import traceback
from typing import Dict, Any, List
from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.services.mongo_ctx import col_orders, col_items, get_db
from app.services.log_event_service import log_event
from app.services.pg_service import pg_fetchone, pg_fetchall, pg_exec

INVOICE_BASE_DIR = os.getenv("INVOICE_BASE_DIR", os.path.join(os.getcwd(), "invoices"))
os.makedirs(INVOICE_BASE_DIR, exist_ok=True)

VAT_RATE = float(os.getenv("VAT_RATE", "0.21"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")

ACCOUNTANT_EMAIL = os.getenv("ACCOUNTANT_EMAIL", "").strip()


def _round2(x: float) -> float:
    return float(f"{x:.2f}")


def _get_invoice_csv_path(created_dt: datetime) -> str:
    year = created_dt.year
    month = created_dt.month
    year_dir = os.path.join(INVOICE_BASE_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)
    return os.path.join(year_dir, f"invoices_{year}_{month:02d}.csv")


def _load_order(order_id: str) -> Dict[str, Any]:
    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Neplatné order_id")

    order = col_orders().find_one({"_id": oid})
    if not order:
        raise HTTPException(status_code=404, detail="Objednávka nebyla nalezena")
    return order


def _ensure_invoice_csv_header(csv_path: str):
    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=';')
            w.writerow([
                "číslo_faktury",
                "id_objednávky",
                "datum_vystavení",
                "datum_splatnosti",
                "zákazník_jméno",
                "zákazník_adresa",
                "zákazník_ICO",
                "zákazník_DIČ",
                "položka_název",
                "množství",
                "cena_za_jednotku_bez_DPH",
                "řádek_celkem_bez_DPH",
                "sazba_DPH_procenta",
                "DPH_celkem",
                "celkem_s_DPH"
            ])


def _enrich_invoice_items(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_items = order.get("items") or []
    out: List[Dict[str, Any]] = []

    for row in raw_items:
        item_id = row.get("item_id")
        quantity = float(row.get("quantity", 1.0) or 1.0)
        unit_price = float(row.get("unit_price", 0.0) or 0.0)

        name = row.get("name")

        if item_id and not name:
            try:
                iid = ObjectId(item_id)
                item_doc = col_items().find_one({"_id": iid})
                if item_doc:
                    vyrobce = item_doc.get("vyrobce") or ""
                    model = item_doc.get("model") or ""
                    joined = (vyrobce + " " + model).strip()
                    if joined:
                        name = joined
            except Exception:
                pass

        if not name:
            name = "Položka"

        line_total = quantity * unit_price
        out.append({
            "item_id": item_id,
            "name": name,
            "quantity": _round2(quantity),
            "unit_price": _round2(unit_price),
            "line_total": _round2(line_total),
        })

    return out


def _build_invoice_core(order: Dict[str, Any]) -> Dict[str, Any]:
    order_id_str = str(order["_id"])
    created = order.get("created") or datetime.utcnow()

    if isinstance(created, str):
        try:
            created_dt = datetime.fromisoformat(created)
        except Exception:
            created_dt = datetime.utcnow()
    else:
        created_dt = created

    due_days = int(order.get("due_days", 14))
    due_date = created_dt + timedelta(days=due_days)

    customer = order.get("customer") or {}

    first = (customer.get("first_name") or "").strip()
    last = (customer.get("last_name") or "").strip()
    cust_name = (first + " " + last).strip() or "Neznámý zákazník"

    street = (customer.get("street") or "").strip()
    city = (customer.get("city") or "").strip()
    postcode = (customer.get("postcode") or "").strip()
    country = (customer.get("country") or "").strip()

    addr_parts = [p for p in [street, city, postcode, country] if p]
    cust_address = ", ".join(addr_parts) or "Adresa neuvedena"

    cust_ico = (customer.get("ico") or "").strip()
    cust_dic = (customer.get("dic") or "").strip()

    items = _enrich_invoice_items(order)

    base_total = sum(float(i["line_total"]) for i in items)
    vat_amount = base_total * VAT_RATE
    total_with_vat = base_total + vat_amount

    invoice_no = order.get("invoice_number") or f"INV-{created_dt.strftime('%Y%m%d')}-{order_id_str[-6:]}"

    return {
        "invoice_number": invoice_no,
        "order_id": order_id_str,
        "created_dt": created_dt,
        "invoice_date": created_dt.strftime("%d.%m.%Y"),
        "due_date": due_date.strftime("%d.%m.%Y"),
        "customer_name": cust_name,
        "customer_address": cust_address,
        "customer_ico": cust_ico,
        "customer_dic": cust_dic,
        "items": items,
        "base_total": _round2(base_total),
        "vat_amount": _round2(vat_amount),
        "total_with_vat": _round2(total_with_vat),
        "vat_rate_percent": int(VAT_RATE * 100),
    }


def _append_invoice_to_csv(core: Dict[str, Any]) -> str:
    created_dt: datetime = core["created_dt"]
    csv_path = _get_invoice_csv_path(created_dt)
    _ensure_invoice_csv_header(csv_path)

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=';')
        for it in core["items"]:
            w.writerow([
                core["invoice_number"],
                core["order_id"],
                core["invoice_date"],
                core["due_date"],
                core["customer_name"],
                core["customer_address"],
                core["customer_ico"],
                core["customer_dic"],
                it["name"],
                _round2(it["quantity"]),
                _round2(it["unit_price"]),
                _round2(it["line_total"]),
                core["vat_rate_percent"],
                core["vat_amount"],
                core["total_with_vat"],
            ])

    return csv_path


def _mark_order_invoiced(order_id: str, core: Dict[str, Any], csv_path: str):
    try:
        oid = ObjectId(order_id)
    except Exception:
        return

    rel_csv = os.path.relpath(csv_path, start=INVOICE_BASE_DIR)

    col_orders().update_one(
        {"_id": oid},
        {"$set": {
            "invoice_number": core["invoice_number"],
            "invoice_generated_at": datetime.utcnow(),
            "invoice_export_file": rel_csv,
            "invoice_totals": {
                "base_total": core["base_total"],
                "vat_amount": core["vat_amount"],
                "total_with_vat": core["total_with_vat"],
                "vat_rate_percent": core["vat_rate_percent"],
            }
        }}
    )

def _send_invoice_email(order: Dict[str, Any], core: Dict[str, Any]) -> bool:
    customer = order.get("customer") or {}
    to_addr = (customer.get("email") or "").strip()

    if not to_addr:
        log_event("warn", "Chybí e-mail zákazníka pro fakturu", {
            "order_id": str(order.get("_id"))
        })
        print("❌ Faktura se neodeslala: chybí e-mail zákazníka.")
        return False

    if not SMTP_HOST:
        print("❌ SMTP_HOST není nastaven")
        return False

    from email.mime.text import MIMEText

    domain = (order.get("domain") or "").strip()
    from_email = SMTP_FROM

    if domain:
        row = pg_fetchone(
            """
            SELECT invoice_from_email
            FROM domains
            WHERE domain = :domain
            LIMIT 1
            """,
            {"domain": domain}
        )

        if row and row.get("invoice_from_email"):
            from_email = row["invoice_from_email"]

    subject = f"Faktura {core['invoice_number']} – Hodinářství Jindra"

    body = f"""Dobrý den,

děkujeme za Vaši objednávku hodinek.

Přehled faktury:
- Číslo faktury: {core['invoice_number']}
- Datum vystavení: {core['invoice_date']}
- Datum splatnosti: {core['due_date']}

- Základ daně (bez DPH): {core['base_total']:.2f} CZK
- DPH {core['vat_rate_percent']} %: {core['vat_amount']:.2f} CZK
- Celkem k úhradě: {core['total_with_vat']:.2f} CZK

Tento e-mail slouží jako daňový doklad pro Vaši objednávku.

S pozdravem,
Hodinářství Jindra
"""

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_addr

    print(
        f"📧 Odesílám fakturu: FROM={from_email}, TO={to_addr}, HOST={SMTP_HOST}:{SMTP_PORT}"
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo()

            if SMTP_USER and SMTP_PASS:
                print(f"➡️ SMTP login jako {SMTP_USER}")
                s.starttls()
                s.ehlo()
                s.login(SMTP_USER, SMTP_PASS)

            s.sendmail(from_email, [to_addr], msg.as_string())

        print("✅ Faktura e-mailem úspěšně odeslána.")

        log_event("info", "Faktura odeslána zákazníkovi", {
            "order_id": str(order.get("_id")),
            "to": to_addr,
            "from": from_email,
            "invoice_number": core["invoice_number"]
        })

        return True

    except Exception as e:
        print("❌ Odeslání faktury selhalo:", repr(e))
        traceback.print_exc()

        log_event("error", f"Odeslání faktury selhalo: {e}", {
            "order_id": str(order.get("_id")),
            "to": to_addr
        })

        return False

def generate_invoice(order_id: str) -> Dict[str, Any]:
    order = _load_order(order_id)
    core = _build_invoice_core(order)

    csv_path = _append_invoice_to_csv(core)
    _mark_order_invoiced(order_id, core, csv_path)

    email_sent = _send_invoice_email(order, core)

    return {
        "ok": True,
        "order_id": order_id,
        "invoice_number": core["invoice_number"],
        "csv_path": csv_path,
        "totals": {
            "base_total": core["base_total"],
            "vat_amount": core["vat_amount"],
            "total_with_vat": core["total_with_vat"],
        },
        "email_sent": email_sent,
    }


def set_invoice_base_dir(base_dir: str) -> Dict[str, Any]:
    global INVOICE_BASE_DIR

    base_dir = (base_dir or "").strip()
    if not base_dir:
        raise HTTPException(status_code=400, detail="base_dir je povinné")

    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Nelze vytvořit složku: {e}")

    INVOICE_BASE_DIR = base_dir
    now = datetime.utcnow()

    return {
        "base_dir": INVOICE_BASE_DIR,
        "year": now.year,
        "month": now.month
    }


def get_invoice_config() -> Dict[str, Any]:
    now = datetime.utcnow()
    return {
        "base_dir": INVOICE_BASE_DIR,
        "year": now.year,
        "month": now.month
    }


def get_invoice_csv_file(year: int, month: int):
    try:
        year = int(year)
        month = int(month)
        if not (1 <= month <= 12):
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="Neplatný rok nebo měsíc")

    base_date = datetime(year, month, 1)
    csv_path = _get_invoice_csv_path(base_date)

    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail=f"Pro {month}.{year} žádný CSV soubor neexistuje.")

    filename = os.path.basename(csv_path)
    return FileResponse(csv_path, media_type="text/csv", filename=filename)


def _send_csv_to_accountant(csv_path: str, year: int, month: int):
    target_email = ACCOUNTANT_EMAIL

    if not target_email:
        raise HTTPException(status_code=400, detail="ACCOUNTANT_EMAIL není nastaven")

    if not (SMTP_HOST and SMTP_FROM):
        raise HTTPException(status_code=400, detail="SMTP není nakonfigurováno")

    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    from email.mime.text import MIMEText

    msg = MIMEMultipart()
    msg["Subject"] = f"Fakturační CSV {month:02d}/{year}"
    msg["From"] = SMTP_FROM
    msg["To"] = target_email

    msg.attach(MIMEText("Zasílám fakturační CSV.", "plain", "utf-8"))

    with open(csv_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(csv_path)}"')
        msg.attach(part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.ehlo()

        if SMTP_USER and SMTP_PASS:
            s.starttls()
            s.ehlo()
            s.login(SMTP_USER, SMTP_PASS)

        s.sendmail(SMTP_FROM, [target_email], msg.as_string())

    log_event("info", "Fakturační CSV odesláno účetní", {
        "to": target_email,
        "csv": csv_path,
        "year": year,
        "month": month
    })

def _load_order_pg(order_id: int) -> Dict[str, Any]:
    order = pg_fetchone("""
        SELECT *
        FROM orders
        WHERE id = :id
        LIMIT 1
    """, {"id": order_id})

    if not order:
        raise HTTPException(status_code=404, detail="Objednávka nebyla nalezena")

    items = pg_fetchall("""
        SELECT *
        FROM order_items
        WHERE order_id = :order_id
    """, {"order_id": order_id})

    # převod na Mongo-like strukturu
    return {
        "_id": str(order["id"]),
        "created": order.get("created_at"),
        "domain": order.get("domain"),
        "customer": {
            "email": order.get("customer_email"),
            "first_name": order.get("customer_first_name"),
            "last_name": order.get("customer_last_name"),
            "street": order.get("customer_street"),
            "city": order.get("customer_city"),
            "postcode": order.get("customer_postcode"),
            "country": order.get("customer_country"),
        },
        "items": [
            {
                "name": it.get("name"),
                "quantity": it.get("quantity"),
                "unit_price": (it.get("price_cents") or 0) / 100,
            }
            for it in items
        ]
    }

def generate_invoice_pg(order_id: int) -> Dict[str, Any]:
    order = _load_order_pg(order_id)
    core = _build_invoice_core(order)

    csv_path = _append_invoice_to_csv(core)
    email_sent = _send_invoice_email(order, core)

    pg_exec(
        """
        UPDATE orders
        SET
            invoice_number = :invoice_number,
            invoice_generated_at = now(),
            invoice_export_file = :invoice_export_file
        WHERE id = :order_id
        """,
        {
            "order_id": order_id,
            "invoice_number": core["invoice_number"],
            "invoice_export_file": os.path.relpath(csv_path, start=INVOICE_BASE_DIR),
        }
    )

    return {
        "ok": True,
        "order_id": order_id,
        "invoice_number": core["invoice_number"],
        "csv_path": csv_path,
        "email_sent": email_sent,
    }