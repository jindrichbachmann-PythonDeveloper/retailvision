import os
import io
import json
import base64
import traceback
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from ultralytics import YOLO

import cv2
import numpy as np
from PIL import Image

from fastapi import UploadFile, HTTPException
from app.services.ai_same_watch_guard import clean_watch_identity_guard_best_of_three

# 1:1 z monolitu
from app.services.image_service import enhance_image
from app.services.split_service import split_objects_centered_v2
from app.services.gridfs_service import save_image_bytes_to_gridfs
from app.services.mongo_ctx import col_items
from app.services.log_event_service import log_event
from app.services.pg_service import pg_exec
from app.services.duplicate_service import (
    build_duplicate_fingerprint,
    compare_duplicate_fingerprints,
)

# --- config 1:1 ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL_NAME  = os.getenv("MODEL_NAME", "gpt-4o-mini")
MODEL_RECOG = os.getenv("MODEL_RECOG", "gpt-4o")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1.5")

TARGET_SIZE = (800, 600)

YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", r"C:\Users\jindr\OneDrive\Desktop\tomas\yolov8n.pt")
YOLO_CONF_TH = float(os.getenv("YOLO_CONF_TH", "0.25"))

yolo_model = None
try:
    yolo_model = YOLO(YOLO_MODEL_PATH)
    print("✅ YOLO model načten")
except Exception as e:
    print("⚠️ YOLO model nelze načíst:", repr(e))
    yolo_model = None

# --- OpenAI safe init 1:1 ---
OpenAI = None
try:
    from openai import OpenAI as _OpenAI
    OpenAI = _OpenAI
except Exception:
    OpenAI = None

openai = None
if OPENAI_API_KEY and OpenAI is not None:
    try:
        openai = OpenAI(api_key=OPENAI_API_KEY)
        print("✅ OpenAI SDK inicializováno")
    except Exception as e:
        print("❌ OpenAI init fail:", repr(e))
        openai = None


# --- AI filter import 1:1 ---
gpt_overeni_kvality_debug = None
try:
    from app.services.ai_filter_debug import gpt_overeni_kvality_debug as _gpt
    gpt_overeni_kvality_debug = _gpt
except Exception as e:
    print("Nelze importovat app.services.ai_filter_debug:", repr(e))
    gpt_overeni_kvality_debug = None

# --- rembg remove 1:1 ---
remove = None
try:
    from rembg import remove as _remove
    remove = _remove
except Exception as e:
    print("⚠️ rembg není dostupné:", repr(e))
    remove = None


def safe_json_loads(t: str) -> dict:
    try:
        return json.loads(t)
    except Exception:
        return {}


def remove_bg_rembg_only(image_bytes: bytes) -> bytes:
    try:
        if remove is None:
            return image_bytes
        inp = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        out = remove(inp)
        out.thumbnail((1200, 1200))
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print("remove_bg_rembg_only fail:", repr(e))
        return image_bytes


def ai_output_is_safe(original_bytes: bytes, ai_bytes: bytes) -> bool:
    try:
        orig = cv2.imdecode(np.frombuffer(original_bytes, np.uint8), cv2.IMREAD_COLOR)
        ai = cv2.imdecode(np.frombuffer(ai_bytes, np.uint8), cv2.IMREAD_COLOR)

        if orig is None or ai is None:
            print("❌ AI kontrola: obrázek nejde načíst")
            return False

        # Rozlišení může být jiné, proto AI výstup jen pro kontrolu sjednotíme na velikost originálu
        ai_check = cv2.resize(ai, (orig.shape[1], orig.shape[0]))

        diff = cv2.absdiff(orig, ai_check)
        mean_diff = float(np.mean(diff))

        print(f"DEBUG AI mean_diff: {mean_diff:.2f}")

        # Pokud je změna moc velká, AI pravděpodobně vytvořila něco jiného
        if mean_diff > 40:
            print("❌ AI výstup zamítnut: příliš velká změna obrazu")
            return False

        return True

    except Exception as e:
        print("ai_output_is_safe fail:", repr(e))
        return False


def ai_clean_watch_bytes(image_bytes: bytes) -> bytes:
    """
    AI dočištění výřezu:
    - odstraní zadní / překryté / duplicitní hodinky
    - nechá hlavní hodinky
    - doplní černé pozadí
    """
    try:
        if openai is None:
            return image_bytes

        prompt = """
Remove any secondary, background, overlapping, duplicate or partially visible watches.
Keep only the main foreground watch.
Preserve the main watch exactly as it is: same dial, hands, bracelet/strap, proportions, angle and product appearance.
Do not invent a different watch.
Fill removed areas with a clean pure black background.
Keep it as a realistic product photo on a black background.
Generate only 1 output image.
Center the main watch precisely in the frame.

STRICT RULES:
Do not invent a new watch.
Do not generate a different watch.
Do not change the dial.
Do not change the hands.
Do not change their size or shape.
Do not change the time shown by the hands (must remain exactly the same).
Do not change the numbers.
Do not change the logo or any text.
Do not change the size or proportions of the dial.
Do not change the strap or bracelet.
Do not change the case shape.
Do not add any new objects.
Do not improve, beautify, redesign, redraw or stylize the watch.
Do not replace the watch with a similar watch.
Only remove unwanted extra watches and fill the removed area with black background.
If you cannot do this without modifying the main watch, return the original image unchanged.
"""

        img_file = io.BytesIO(image_bytes)
        img_file.name = "watch.png"

        result = openai.images.edit(
            model=IMAGE_MODEL,
            image=img_file,
            prompt=prompt,
            size="1024x1024",
            output_format="png"
        )

        b64 = result.data[0].b64_json
        ai_bytes = base64.b64decode(b64)

        if not ai_output_is_safe(image_bytes, ai_bytes):
            print("❌ AI výstup zamítnut úplně")
            return None

        return ai_bytes

    except Exception as e:
        print("❌ AI čistič vyhodnotil fotku jako nevhodnou:", repr(e))
        return None


def decode_png_to_bgr(png_bytes: bytes) -> Optional[np.ndarray]:
    img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None or img.size == 0:
        return None

    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    if img.shape[2] == 3:
        return img

    return None


def resize_png_keep_center(img_bgra: np.ndarray, size=TARGET_SIZE) -> bytes:
    if img_bgra is None or img_bgra.size == 0:
        return b""
    target_w, target_h = size
    h, w = img_bgra.shape[:2]
    scale = min(target_w / max(w, 1), target_h / max(h, 1))
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    resized = cv2.resize(img_bgra, (new_w, new_h), interpolation=interp)

    if len(resized.shape) == 3 and resized.shape[2] == 4:
        canvas = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    else:
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)

    x_off = (target_w - new_w) // 2
    y_off = (target_h - new_h) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized

    ok, buf = cv2.imencode(".png", canvas)
    return buf.tobytes() if ok else b""


MAX_MB = 20

def create_analysis_preview_image(image_bytes: bytes, yolo_boxes, decisions) -> Optional[bytes]:
    """
    Vytvoří uživatelskou přehledovou fotku analýzy:
    zelená = prošlo
    červená = neprošlo
    """
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)

        if img is None:
            print("⚠️ PREVIEW: obrázek nejde načíst")
            return None

        canvas = img.copy()

        for i, box in enumerate(yolo_boxes):
            decision = decisions.get(i, {})
            ok = bool(decision.get("ok", False))
            reason = str(decision.get("reason", ""))

            reason_upper = reason.upper()

            if "DUPLIKÁT?" in reason_upper:
                color = (255, 0, 255)   # svítivě fialová (BGR)
                label = f"{i + 1} DUPLIKÁT?"

            elif "DUPLIKÁT" in reason_upper:
                color = (180, 80, 0)   # tmavě modrá (BGR)
                label = f"{i + 1} DUPLIKÁT"

            elif ok:
                color = (0, 200, 0)    # zelená
                label = f"{i + 1} OK"

            else:
                color = (0, 0, 255)    # červená
                label = f"{i + 1} SKIP"
            
            x1 = int(box["x1"])
            y1 = int(box["y1"])
            x2 = int(box["x2"])
            y2 = int(box["y2"])

            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 3)

            label_y = max(30, y1 - 8)
            cv2.rectangle(
                canvas,
                (x1, label_y - 28),
                (min(x1 + 150, canvas.shape[1] - 1), label_y + 5),
                color,
                -1
            )

            cv2.putText(
                canvas,
                label,
                (x1 + 8, label_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )

            if reason:
                reason_y = min(y2 + 24, canvas.shape[0] - 10)

                cv2.putText(
                    canvas,
                    reason[:32],
                    (x1, reason_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    color,
                    2,
                    cv2.LINE_AA
                )

        legend_y = canvas.shape[0] - 120

        cv2.putText(
            canvas,
            "ZELENA = ulozeno",
            (20, legend_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 200, 0),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            canvas,
            "CERVENA = neproslo filtrem",
            (20, legend_y + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            canvas,
            "MODRA = jisty duplikat",
            (20, legend_y + 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (180, 80, 0),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            canvas,
            "FIALOVA = podezreni na duplicitu",
            (20, legend_y + 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 0, 255),
            2,
            cv2.LINE_AA
        )

        ok, buf = cv2.imencode(".png", canvas)

        if not ok:
            return None

        return buf.tobytes()

    except Exception as e:
        print("create_analysis_preview_image fail:", repr(e))
        return None

def compute_image_hash(image_bytes: bytes) -> Optional[str]:
    """
    Jednoduchý perceptual hash.
    Slouží pro první odhad podobnosti mezi cropy.
    """
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)

        if img is None:
            return None

        img = cv2.resize(img, (16, 16), interpolation=cv2.INTER_AREA)

        avg = float(img.mean())

        bits = img > avg

        return "".join("1" if b else "0" for b in bits.flatten())

    except Exception as e:
        print("compute_image_hash fail:", repr(e))
        return None

def hash_distance(a: Optional[str], b: Optional[str]) -> int:
    """
    Vrátí počet rozdílných bitů mezi dvěma hashi.
    Menší číslo = podobnější obrázek.
    """
    if not a or not b:
        return 9999

    if len(a) != len(b):
        return 9999

    return sum(1 for x, y in zip(a, b) if x != y)

def find_possible_duplicate(user_id, image_hash: Optional[str], domain: str, analysis_id: Optional[str] = None):
    """
    Najde možnou duplicitu mezi už uloženými produkty stejného uživatele.
    Zatím podle jednoduchého image_hash.
    """
    try:
        if not image_hash:
            return None

        candidates = col_items().find({
            "user_id": user_id,
            "domain": domain,
            "image_hash": {"$exists": True, "$ne": None},
            "type": {"$ne": "analysis_preview"},
            "analysis_id": {"$ne": analysis_id},
        }).limit(300)

        best = None
        best_dist = 9999

        for old in candidates:
            old_hash = old.get("image_hash")
            dist = hash_distance(image_hash, old_hash)

            if dist < best_dist:
                best_dist = dist
                best = old

        # 16x16 hash = 256 bitů
        # čím menší číslo, tím podobnější
        if best is not None and best_dist <= 35:

            confidence = max(0, min(100, int(round(100 - best_dist))))

            return {
                "item_id": str(best.get("_id")),
                "distance": best_dist,
                "confidence": confidence,
                "name": f"{best.get('vyrobce') or ''} {best.get('model') or ''}".strip(),
            }
        return None

    except Exception as e:
        print("find_possible_duplicate fail:", repr(e))
        return None
    
def find_duplicate_by_fingerprint(
    user_id,
    duplicate_fp: Dict[str, Any],
    domain: str,
    analysis_id: Optional[str] = None,
):
    """
    Najde duplicitu podle plného fingerprintu z duplicate_service.py.
    Vrací nejlepší shodu.
    """
    try:
        if not duplicate_fp:
            return None

        candidates = col_items().find({
            "user_id": user_id,
            "domain": domain,
            "duplicate_fp": {"$exists": True, "$ne": None},
            "type": {"$ne": "analysis_preview"},
            "analysis_id": {"$ne": analysis_id},
        }).limit(300)

        best = None
        best_result = None
        best_score = -9999

        for old in candidates:
            old_fp = old.get("duplicate_fp")
            if not old_fp:
                continue

            result = compare_duplicate_fingerprints(
                duplicate_fp,
                old_fp
            )

            score = int(result.get("score") or 0)

            if score > best_score:
                best_score = score
                best = old
                best_result = result

        if best is None or best_result is None:
            return None

        status = best_result.get("status", "new")

        if status == "new":
            return None

        return {
            "item_id": str(best.get("_id")),
            "score": best_score,
            "status": status,
            "result": best_result,
            "name": f"{best.get('vyrobce') or ''} {best.get('model') or ''}".strip(),
        }

    except Exception as e:
        print("find_duplicate_by_fingerprint fail:", repr(e))
        return None
            
def keep_best_crop_per_yolo_box(items, yolo_boxes):
    """
    Cíl:
    1 YOLO box = maximálně 1 crop / 1 produkt.
    Zatím párujeme podle pořadí a score, protože split crop zatím nemá původní souřadnice.
    """

    if not items:
        return []

    if not yolo_boxes:
        print("⚠️ YOLO boxy nejsou dostupné, deduplikace podle YOLO se přeskočila")
        return items

    print(f"DEBUG DEDUPE BEFORE: items={len(items)}, yolo_boxes={len(yolo_boxes)}")

    # nouzově seřadíme kandidáty podle kvality
    sorted_items = sorted(
        items,
        key=lambda it: (
            float(it.get("score", 0.0)),
            float(it.get("sharp", 0.0)),
            float(it.get("area_ratio", 0.0)),
        ),
        reverse=True
    )

    # důležité: max 1 produkt na 1 YOLO box
    limited = sorted_items[:len(yolo_boxes)]

    print(f"DEBUG DEDUPE AFTER: items={len(limited)}")

    return limited

def detect_yolo_boxes(image_bytes: bytes):
    try:
        if yolo_model is None:
            return []

        img = cv2.imdecode(
            np.frombuffer(image_bytes, np.uint8),
            cv2.IMREAD_COLOR
        )

        if img is None:
            return []

        res = yolo_model.predict(
            img,
            conf=YOLO_CONF_TH,
            verbose=False
        )

        boxes = []

        for r in res:
            if r.boxes is None:
                continue

            for b in r.boxes.xyxy.cpu().numpy():
                x1, y1, x2, y2 = map(int, b)

                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2

                boxes.append({
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "cx": cx,
                    "cy": cy,
                })

        return boxes

    except Exception as e:
        print("detect_yolo_boxes fail:", repr(e))
        return []

async def analyze_files(
    files: List[UploadFile],
    use_ai_filter: int = 1,
    recognize: int = 1,
    user=None,
) -> List[Dict[str, Any]]:
    print(">>> analyze_files invoked")
    print(f">>> Number of files received: {len(files)}")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided for analysis")

    try:
        results: List[Dict[str, Any]] = []
        processed_files = 0
        skipped_files = 0

        max_bytes = MAX_MB * 1024 * 1024

        for file in files:
            raw = await file.read()
            print(f">>> Processing file: {file.filename}, size={len(raw)} bytes")

            if not raw:
                skipped_files += 1
                continue

            if len(raw) > max_bytes:
                raise HTTPException(status_code=413, detail=f"File too large (> {MAX_MB} MB): {file.filename}")

            processed_files += 1
            log_event("info", f"Analyzuji: {file.filename}", {"filename": file.filename})

            analysis_id = str(uuid.uuid4())

            enhanced = enhance_image(raw)

            yolo_boxes_raw = detect_yolo_boxes(raw)
            yolo_boxes_enhanced = detect_yolo_boxes(enhanced)

            print(f"DEBUG YOLO COUNT RAW: {len(yolo_boxes_raw)}")
            print(f"DEBUG YOLO COUNT ENHANCED: {len(yolo_boxes_enhanced)}")

            yolo_boxes = yolo_boxes_enhanced
            yolo_count = len(yolo_boxes)

            print(f"DEBUG YOLO COUNT USED: {yolo_count}")

            items = split_objects_centered_v2(enhanced)

            print("DEBUG FIRST ITEM KEYS:", items[0].keys() if items else None)

            items = keep_best_crop_per_yolo_box(items, yolo_boxes)

            preview_decisions = {}

            domain = (
                user.get("domain")
                or os.getenv("DEFAULT_DOMAIN", "retailvisionuzivatel.cz")
            )

            log_event("debug", f"Nalezeno kandidátů: {len(items)}", {"filename": file.filename})

            if not items:
                skipped_files += 1
                continue

            for idx, it in enumerate(items):
                preview_decisions[idx] = {
                    "ok": False,
                    "reason": "čeká"
                }

                # ❌ tvrdý filtr kvality – nic pod 8 nesmí projít dál
                if float(it.get("score", 0.0)) < 8.0:
                    print(f"❌ SKIP (score < 8): {it.get('score')}")
                    preview_decisions[idx] = {
                        "ok": False,
                        "reason": f"score {it.get('score')}"
                    }
                    continue
                
                crop_png = it["bytes"]

                # ✅ odstranění pozadí přes rembg (1:1)
                crop_png = remove_bg_rembg_only(crop_png)

                # ✅ AI SAME WATCH GUARD
                # Důležité:
                # - guard nejdřív ověří, že originální crop po rembg má huge circle
                # - pokud huge circle nenajde, AI clean se vůbec nespustí
                # - pokud huge circle najde, pustí AI clean 3x
                # - porovnává ORIGINAL DIAL vs AI DIAL
                # - do skladu se uloží celý AI výsledek, ne vyříznutý ciferník
                ai_guard = clean_watch_identity_guard_best_of_three(
                    crop_png
                )

                if not ai_guard.get("ok"):
                    print(
                        "❌ SKIP (AI změnila hodinky nebo nesedí subciferníky):",
                        ai_guard.get("reason")
                    )

                    preview_decisions[idx] = {
                        "ok": False,
                        "reason": ai_guard.get(
                            "reason",
                            "AI změnila hodinky"
                        )
                    }

                    continue

                crop_png = ai_guard["image"]

                # načtení po rembg / AI clean (RGBA)
                img = cv2.imdecode(np.frombuffer(crop_png, np.uint8), cv2.IMREAD_UNCHANGED)
                if img is None:
                    preview_decisions[idx] = {
                        "ok": False,
                        "reason": "image read fail"
                    }
                    continue

                if len(img.shape) == 3 and img.shape[2] == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

                crop_png = resize_png_keep_center(img, size=TARGET_SIZE) or crop_png

                crop_bgr = decode_png_to_bgr(crop_png)
                if crop_bgr is None or crop_bgr.size == 0:
                    preview_decisions[idx] = {
                        "ok": False,
                        "reason": "crop read fail"
                    }
                    continue

                sharp = float(it.get("sharp", 0.0))
                h, w = crop_bgr.shape[:2]

                log_event(
                    "debug",
                    f"Výřez #{idx+1}: {w}×{h}px – ostrost {sharp:.1f}",
                    {"filename": file.filename, "index": idx+1}
                )

                if use_ai_filter:
                    try:
                        if gpt_overeni_kvality_debug is None:
                            raise RuntimeError(
                                  "Chybí import gpt_overeni_kvality_debug (app.services.ai_filter_debug)"
                            )

                        tmp = gpt_overeni_kvality_debug(
                            openai_client=openai,
                            img_bgr=crop_bgr,
                            model_name=MODEL_NAME,
                            mode="normal",
                            debug_dir=os.getenv("AI_DEBUG_DIR", r"C:\Users\jindr\OneDrive\Desktop\tomas\doprdele_hodinky"),
                            tag=f"{file.filename}_{idx+1}",
                        )

                        if tmp is None:
                            vhodne, kval, kom = False, 0.0, "AI filtr nic nevrátil (None)"
                        elif not isinstance(tmp, (tuple, list)) or len(tmp) != 3:
                            vhodne, kval, kom = False, 0.0, f"AI filtr vrátil špatný tvar: {type(tmp).__name__} {tmp!r}"
                        else:
                            vhodne, kval, kom = tmp

                    except Exception as e:
                        vhodne, kval, kom = False, 0.0, f"AI filtr spadl: {repr(e)}"
                else:
                    vhodne, kval, kom = True, 5.0, "AI filtr vypnut"

                if use_ai_filter and not vhodne:
                    print("❌ SKIP (AI filtr)")
                    preview_decisions[idx] = {
                        "ok": False,
                        "reason": "AI filtr"
                    }
                    continue

                if use_ai_filter and float(kval or 0.0) < 8.0:
                    print(f"❌ SKIP (AI kvalita < 8): {kval}")
                    preview_decisions[idx] = {
                        "ok": False,
                        "reason": f"kvalita {kval}"
                    }
                    continue

                parsed = {"vyrobce": None, "model": None}

                if recognize and openai:
                    try:
                        b64 = base64.b64encode(crop_png).decode()

                        res = openai.chat.completions.create(
                            model=MODEL_RECOG,
                            messages=[
                                {"role": "system", "content": "Identifikace hodinek"},
                                {"role": "user", "content": [
                                    {
                                        "type": "text",
                                        "text": "Rozpoznej značku a model hodinek, vrať JSON"
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{b64}"
                                        }
                                    }
                                ]}
                            ],
                            temperature=0,
                            response_format={"type": "json_object"}
                        )

                        parsed = safe_json_loads(
                            res.choices[0].message.content or "{}"
                        )

                    except Exception as e:
                        log_event(
                            "error",
                            f"GPT rozpoznání selhalo: {e}",
                            {"filename": file.filename}
                        )

                image_hash = compute_image_hash(crop_png)

                duplicate_fp = build_duplicate_fingerprint(
                    crop_png,
                    parsed
                )

                possible_duplicate = find_duplicate_by_fingerprint(
                    user["uid"],
                    duplicate_fp,
                    domain,
                    analysis_id
                )

                print("DEBUG DUPLICATE FP:", duplicate_fp)
                
                duplicate_status = "new"
                duplicate_of = None
                duplicate_distance = None
                duplicate_confidence = 0

                if possible_duplicate:

                    duplicate_status = possible_duplicate.get(
                        "status",
                        "possible_duplicate"
                    )

                    duplicate_of = possible_duplicate.get("item_id")

                    duplicate_confidence = int(
                        possible_duplicate.get("score") or 0
                    )

                    duplicate_distance = None

                    print(
                        f"⚠️ DUPLIKACE: {duplicate_of}, "
                        f"status={duplicate_status}, "
                        f"score={duplicate_confidence}"
                    )

                if (
                        duplicate_status in ("duplicate", "possible_duplicate")
                        and duplicate_confidence >= 80
                ):
                        print(
                                f"🔵 JISTÝ DUPLIKÁT NEULOŽEN: "
                                f"status={duplicate_status}, "
                                f"confidence={duplicate_confidence}%"
                        )

                        preview_decisions[idx] = {
                                "ok": False,
                                "reason": f"DUPLIKÁT {duplicate_confidence}%"
                        }

                        continue
                
                filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{idx}_{file.filename}"
                file_id = save_image_bytes_to_gridfs(crop_png, filename)
                
                doc = {
                    "type": "product",
                    "is_ready_for_sale": False,                    
                    "vyrobce": parsed.get("vyrobce"),
                    "model": parsed.get("model"),
                    "approved": vhodne,
                    "quality_score": kval,
                    "ai_comment": kom,
                    "orig_file_id": str(file_id),
                    "created": datetime.utcnow(),
                    "quantity": 1,
                    "status": "possible_duplicate" if duplicate_status == "possible_duplicate" else "skladem",
                    "shipped": False,
                    "shipped_at": None,
                    "domain": domain,
                    "image_hash": image_hash,
                    "duplicate_fp": duplicate_fp,
                    "duplicate_status": duplicate_status,
                    "duplicate_of": duplicate_of,
                    "duplicate_distance": duplicate_distance,
                    "duplicate_confidence": duplicate_confidence,
                    "analysis_id": analysis_id,
                }
                
                if not user:
                    raise HTTPException(status_code=401, detail="Chybí přihlášený uživatel")

                doc["user_id"] = user["uid"]

                ins = col_items().insert_one(doc)
                doc["_id"] = str(ins.inserted_id)

                pg_exec(
                    """
                    INSERT INTO products (
                        user_id,
                        domain,
                        mongo_item_id,
                        name,
                        description,
                        price_cents,
                        price_confidence,
                        details_confidence,
                        manually_edited,
                        is_ready_for_sale,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :user_id,
                        :domain,
                        :mongo_item_id,
                        :name,
                        :description,
                        :price_cents,
                        :price_confidence,
                        :details_confidence,
                        :manually_edited,
                        :is_ready_for_sale,
                        now(),
                        now()
                    )
                    """,
                    {
                        "user_id": user["uid"],
                        "domain": domain,
                        "mongo_item_id": doc["_id"],
                        "name": f"{parsed.get('vyrobce') or 'Hodinky'} {parsed.get('model') or ''}".strip(),
                        "description": "",
                        "price_cents": 0,
                        "price_confidence": 0,
                        "details_confidence": 0,
                        "manually_edited": False,
                        "is_ready_for_sale": False,
                    }
                )

                preview_decisions[idx] = {
                    "ok": True,
                    "reason": "uloženo"
                }

                if duplicate_status == "possible_duplicate":
                    preview_decisions[idx] = {
                        "ok": True,
                        "reason": f"DUPLIKÁT? {duplicate_confidence}%"
                    }

                elif duplicate_status == "duplicate":
                    preview_decisions[idx] = {
                        "ok": True,
                        "reason": f"DUPLIKÁT {duplicate_confidence}%"
                    }

                else:
                    preview_decisions[idx] = {
                        "ok": True,
                        "reason": "uloženo"
                    }
                    
                results.append(doc)

            preview_png = create_analysis_preview_image(
                enhanced,
                yolo_boxes,
                preview_decisions
            )

            if preview_png:
                preview_filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_PREVIEW_{file.filename}"
                preview_file_id = save_image_bytes_to_gridfs(preview_png, preview_filename)

                preview_doc = {
                    "vyrobce": "Analýza",
                    "model": "Přehled výsledku",
                    "approved": False,
                    "quality_score": 0,
                    "ai_comment": "Zeleně prošlo, červeně neprošlo",
                    "orig_file_id": str(preview_file_id),
                    "created": datetime.utcnow(),
                    "quantity": 1,
                    "status": "preview",
                    "shipped": False,
                    "shipped_at": None,
                    "domain": domain,
                    "type": "analysis_preview",
                    "is_ready_for_sale": False,
                    "user_id": user["uid"],
                    "analysis_id": analysis_id,
                }

                ins = col_items().insert_one(preview_doc)
                preview_doc["_id"] = str(ins.inserted_id)

                results.append(preview_doc)                

        log_event(
            "info",
            "Analýza dokončena",
            {
                "processed": processed_files,
                "skipped": skipped_files,
                "results": len(results)
            }
        )

        return results

    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Chyba analýzy")