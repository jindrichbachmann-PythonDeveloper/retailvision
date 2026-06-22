import os, json, base64, cv2
import numpy as np
from datetime import datetime
from app.services.prefilter_roi import prefilter_watch_geometry

def safe_json_loads(t: str) -> dict:
    try:
        return json.loads(t)
    except:
        return {}

def save_debug_image(folder: str, img_bgr: np.ndarray, name: str):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    cv2.imwrite(path, img_bgr)

def gpt_overeni_kvality_debug(
    openai_client,
    img_bgr: np.ndarray,
    model_name: str,
    mode: str = "normal",
    debug_dir: str = "debug_ai_filter",
    tag: str = "crop",
):
    if openai_client is None or img_bgr is None or img_bgr.size == 0:
        return False, 0.0, "GPT nedostupné nebo prázdný obrázek"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base = f"{ts}_{tag}"

    save_debug_image(debug_dir, img_bgr, f"{base}.png")

    ok, enc = cv2.imencode(".png", img_bgr)
    if not ok:
        return False, 0.0, "Nelze enkódovat obrázek"
    img_b64 = base64.b64encode(enc).decode("utf-8")

    if mode == "strict":
        extra_rule = "Pokud si nejsi jistý, nastav vhodne=false."
    else:
        extra_rule = "Když si nejsi jistý, dej spíš nižší score. Vhodne=false jen při vážné chybě."

    prompt = (
        "Vyhodnoť kvalitu produktové fotky hodinek.\n"
        "Ohodnoť score 0–10 (10 = top e-shop fotka).\n"
        "vhodne=true pokud: je 1 kus hodinek, jsou převážně celé a rozpoznatelné.\n"
        "vhodne=false pokud: více kusů / výrazně uříznuté / nepoužitelné.\n"
        f"{extra_rule}\n\n"
        "Vrať POUZE JSON:\n"
        "{\"vhodne\": true/false, \"score\": 0-10, \"komentar\": \"stručný důvod\"}"
    )

    try:
        res = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "Jsi hodnotitel kvality fotek hodinek pro e-shop."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                ]}
            ],
            temperature=0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )

        raw = (res.choices[0].message.content or "").strip()
        data = safe_json_loads(raw)

        with open(os.path.join(debug_dir, f"{base}.json"), "w", encoding="utf-8") as f:
            f.write(raw if raw else "{}")

        vhodne = bool(data.get("vhodne", False))
        score = float(data.get("score", 0.0) or 0.0)
        score = max(0.0, min(10.0, score))
        komentar = str(data.get("komentar", "")).strip() or "Bez komentáře"

        return vhodne, score, komentar

    except Exception as e:
        with open(os.path.join(debug_dir, f"{base}_error.txt"), "w", encoding="utf-8") as f:
            f.write(repr(e))
        return False, 0.0, "GPT selhalo"
