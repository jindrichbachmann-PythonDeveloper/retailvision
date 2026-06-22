import os
import csv
import io
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

from bson import ObjectId

from app.services.mongo_ctx import get_db, col_orders
from app.services.log_event_service import log_event

# Config je uložený v Mongo jako 1 dokument
# _id = "config"
CONF_ID = "config"

def _conf_col():
    return get_db()["invoice_config"]

def _invoices_col():
    return get_db()["invoices"]

def get_invoice_config() -> Dict[str, Any]:
    doc = _conf_col().find_one({"_id": CONF_ID}) or {}
    # defaulty
    return {
        "invoice_dir": doc.get("invoice_dir") or os.getenv("INVOICE_DIR", r"C:\invoices"),
        "accountant_email": doc.get("accountant_email") or os.getenv("ACCOUNTANT_EMAIL", ""),
        "company_name": doc.get("company_name") or os.getenv("COMPANY_NAME", "RetailVision"),
        "company_ico": doc.get("company_ico") or os.getenv("COMPANY_ICO", ""),
        "company_dic": doc.get("company_dic") or os.getenv("COMPANY_DIC", ""),
        "bank_account": doc.get("bank_account") or os.getenv("BANK_ACCOUNT", ""),
        "next_invoice_no": int(doc.get("next_invoice_no") or 1),
    }

def set_invoice_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    cur = get_invoice_config()
    new_doc = {
        "_id": CONF_ID,
        "invoice_dir": payload.get("invoice_dir", cur["invoice_dir"]),
        "accountant_email": payload.get("accountant_email", cur["accountant_email"]),
        "company_name": payload.get("company_name", cur["company_name"]),
        "company_ico": payload.get("company_ico", cur["company_ico"]),
        "company_dic": payload.get("company_dic", cur["company_dic"]),
        "bank_account": payload.get("bank_account", cur["bank_account"]),
        "next_invoice_no": int(payload.get("next_invoice_no", cur["next_invoice_no"])),
        "updated": datetime.utcnow(),
    }
    _conf_col().replace_one({"_id": CONF_ID}, new_doc, upsert=True)
    return get_invoice_config()

def _reserve_invoice_number() -> int:
    # atomicky zvedne next_invoice_no a vrátí starou hodnotu
    res = _conf_col().find_one_and_update(
        {"_id": CONF_ID},
        {"": {"next_invoice_no": 1}},
        upsert=True,
        return_document=True
    )
    # když dokument vznikl nově, může mít next_invoice_no None
    doc = _conf_col().find_one({"_id": CONF_ID}) or {}
    # po  bude next_invoice_no existovat; číslo faktury je (next-1)
    return int(doc.get("next_invoice_no", 2)) - 1

def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def _order_total(order: Dict[str, Any]) -> float:
    # kompatibilní: vezme total, nebo spočítá položky
    if isinstance(order.get("total"), (int, float)):
        return float(order["total"])
    items = order.get("items") or []
    s = 0.0
    for it in items:
        try:
            qty = float(it.get("quantity", 1))
            price = float(it.get("price", 0))
            s += qty * price
        except Exception:
            pass
    return float(s)

def _render_invoice_html(cfg: Dict[str, Any], order: Dict[str, Any], inv_no: int) -> str:
    created = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    customer = order.get("customer") or {}
    items = order.get("items") or []

    rows = ""
    for it in items:
        name = str(it.get("name") or it.get("model") or "položka")
        qty = it.get("quantity", 1)
        price = it.get("price", 0)
        rows += f"<tr><td>{name}</td><td>{qty}</td><td>{price}</td></tr>"

    total = _order_total(order)

    html = f"""<!doctype html>
<html lang="cs">
<head><meta charset="utf-8"><title>Faktura {inv_no}</title></head>
<body>
<h1>Faktura #{inv_no}</h1>
<p>Vystaveno: {created}</p>

<h3>Dodavatel</h3>
<p>{cfg.get("company_name","")}</p>
<p>IČO: {cfg.get("company_ico","")} &nbsp; DIČ: {cfg.get("company_dic","")}</p>
<p>Účet: {cfg.get("bank_account","")}</p>

<h3>Odběratel</h3>
<p>{customer.get("name","")}</p>
<p>{customer.get("email","")}</p>
<p>{customer.get("address","")}</p>

<h3>Položky</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Název</th><th>Množství</th><th>Cena</th></tr>
{rows or "<tr><td colspan='3'>(bez položek)</td></tr>"}
</table>

<h2>Celkem: {total:.2f}</h2>
</body></html>
"""
    return html

def _try_render_pdf_from_html(html: str, pdf_path: str):
    # pokud je reportlab, vygenerujeme jednoduché PDF (ne HTML->PDF render),
    # ale aspoň PDF výstup jako v monolitu často bývá
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm

        c = canvas.Canvas(pdf_path, pagesize=A4)
        text = c.beginText(20*mm, 280*mm)
        for line in html.splitlines():
            # oříznout dlouhé řádky
            if len(line) > 120:
                line = line[:120] + "..."
            text.textLine(line)
            if text.getY() < 20*mm:
                c.drawText(text)
                c.showPage()
                text = c.beginText(20*mm, 280*mm)
        c.drawText(text)
        c.save()
        return True
    except Exception:
        return False

def generate_invoice_for_order(order_id: str) -> Dict[str, Any]:
    try:
        oid = ObjectId(order_id)
    except Exception:
        raise ValueError("Neplatné order_id")

    order = col_orders().find_one({"_id": oid})
    if not order:
        raise ValueError("Order nenalezen")

    cfg = get_invoice_config()
    inv_no = _reserve_invoice_number()

    inv_dir = cfg["invoice_dir"]
    _ensure_dir(inv_dir)

    # soubory
    base_name = f"invoice_{inv_no:06d}_order_{order_id}"
    html_path = os.path.join(inv_dir, base_name + ".html")
    pdf_path = os.path.join(inv_dir, base_name + ".pdf")

    html = _render_invoice_html(cfg, order, inv_no)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    has_pdf = _try_render_pdf_from_html(html, pdf_path)

    total = _order_total(order)

    inv_doc = {
        "invoice_no": inv_no,
        "order_id": order_id,
        "created": datetime.utcnow(),
        "total": total,
        "html_path": html_path,
        "pdf_path": pdf_path if has_pdf else None,
        "accountant_email": cfg.get("accountant_email",""),
    }
    ins = _invoices_col().insert_one(inv_doc)
    inv_doc["_id"] = str(ins.inserted_id)

    # uložit referenci do order (1:1 styl)
    col_orders().update_one({"_id": oid}, {"": {"invoice_no": inv_no, "invoice_id": str(ins.inserted_id)}})

    log_event("info", "Faktura vygenerována", {"order_id": order_id, "invoice_no": inv_no, "total": total})

    # vrátit JSON (bez ObjectId)
    inv_doc["created"] = inv_doc["created"].isoformat()
    return inv_doc

def build_invoices_csv(year: int, month: int) -> Tuple[bytes, str]:
    # export z invoices kolekce podle created
    start = datetime(int(year), int(month), 1)
    if month == 12:
        end = datetime(year+1, 1, 1)
    else:
        end = datetime(year, month+1, 1)

    cur = _invoices_col().find({"created": {"": start, "": end}}).sort("created", 1)

    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["invoice_no", "order_id", "created", "total", "pdf_path", "html_path"])

    count = 0
    for d in cur:
        count += 1
        created = d.get("created")
        created_s = created.isoformat() if hasattr(created, "isoformat") else str(created)
        w.writerow([
            d.get("invoice_no"),
            d.get("order_id"),
            created_s,
            d.get("total"),
            d.get("pdf_path") or "",
            d.get("html_path") or ""
        ])

    data = out.getvalue().encode("utf-8")
    filename = f"invoices_{year:04d}_{month:02d}.csv"
    return data, filename

def send_csv_to_accountant(year: int, month: int) -> Dict[str, Any]:
    cfg = get_invoice_config()
    to_email = (cfg.get("accountant_email") or "").strip()
    if not to_email:
        return {"ok": False, "detail": "Chybí accountant_email v invoice config"}

    # SMTP z env (stejně jako jinde)
    host = os.getenv("SMTP_HOST","").strip()
    port = int(os.getenv("SMTP_PORT","587"))
    user = os.getenv("SMTP_USER","").strip()
    pwd  = os.getenv("SMTP_PASS","").strip()
    mail_from = os.getenv("SMTP_FROM","").strip() or user

    if not host or not mail_from:
        return {"ok": False, "detail": "Chybí SMTP_HOST/SMTP_FROM v .env"}

    csv_bytes, filename = build_invoices_csv(year, month)

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    import smtplib

    msg = MIMEMultipart()
    msg["Subject"] = f"Faktury CSV {year:04d}-{month:02d}"
    msg["From"] = mail_from
    msg["To"] = to_email

    msg.attach(MIMEText("Zasílám export faktur v CSV.", "plain", "utf-8"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(csv_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(host, port) as s:
        s.ehlo()
        if user and pwd:
            s.starttls()
            s.ehlo()
            s.login(user, pwd)
        s.sendmail(mail_from, [to_email], msg.as_string())

    log_event("info", "CSV odesláno účetní", {"to": to_email, "year": year, "month": month})
    return {"ok": True, "sent_to": to_email, "filename": filename}

