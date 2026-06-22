import re
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


DUPLICATE_VERSION = 1


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""

    text = str(text).upper()
    text = re.sub(r"[^A-Z0-9ÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_watch_ocr_text(image_bytes: bytes) -> str:
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )

        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return ""

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        gray = cv2.equalizeHist(gray)

        blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
        sharp = cv2.addWeighted(gray, 1.5, blur, -0.5, 0)

        text = pytesseract.image_to_string(sharp, config="--psm 6")
        return normalize_text(text)

    except Exception as e:
        print("extract_watch_ocr_text fail:", repr(e))
        return ""


def compute_visual_hash(image_bytes: bytes) -> Optional[str]:
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None

        img = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
        avg = float(img.mean())
        bits = img > avg

        return "".join("1" if b else "0" for b in bits.flatten())

    except Exception as e:
        print("compute_visual_hash fail:", repr(e))
        return None


def compute_color_hash(image_bytes: bytes) -> Optional[List[float]]:
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None

        img = cv2.resize(img, (96, 96), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        h_hist = cv2.calcHist([hsv], [0], None, [18], [0, 180])
        s_hist = cv2.calcHist([hsv], [1], None, [8], [0, 256])
        v_hist = cv2.calcHist([hsv], [2], None, [8], [0, 256])

        vec = np.concatenate([
            h_hist.flatten(),
            s_hist.flatten(),
            v_hist.flatten(),
        ])

        vec = vec / (float(np.sum(vec)) + 1e-6)

        return [round(float(x), 6) for x in vec]

    except Exception as e:
        print("compute_color_hash fail:", repr(e))
        return None


def detect_subdial_count(image_bytes: bytes) -> Optional[int]:
    """
    Hrubý odhad počtu malých kruhů/subciferníků.
    Cíl není dokonalost, ale pomocný důkaz pro duplicity.
    """
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None

        img = cv2.resize(img, (500, 500), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        gray = cv2.medianBlur(gray, 5)
        gray = cv2.equalizeHist(gray)

        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=45,
            param1=80,
            param2=22,
            minRadius=18,
            maxRadius=65,
        )

        if circles is None:
            return 0

        circles = np.round(circles[0, :]).astype("int")

        valid = []

        for x, y, r in circles:
            # ignoruj okraje obrázku
            if x < 60 or y < 60 or x > 440 or y > 440:
                continue

            # ignoruj obrovský hlavní ciferník
            if r > 70:
                continue

            valid.append((x, y, r))

        # omezení: běžný chronograf má 1–4 subciferníky
        count = len(valid)

        if count > 4:
            count = 4

        return int(count)

    except Exception as e:
        print("detect_subdial_count fail:", repr(e))
        return None


def bit_distance(a: Optional[str], b: Optional[str]) -> int:
    if not a or not b:
        return 999999

    if len(a) != len(b):
        return 999999

    return sum(1 for x, y in zip(a, b) if x != y)


def color_distance(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    try:
        if not a or not b or len(a) != len(b):
            return 999999.0

        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)

        return float(np.sum(np.abs(va - vb)))

    except Exception:
        return 999999.0


def text_similarity(a: str, b: str) -> float:
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    set_a = set(a.split())
    set_b = set(b.split())

    if not set_a or not set_b:
        return 0.0

    overlap = len(set_a & set_b)
    total = len(set_a | set_b)

    return overlap / max(total, 1)


def build_duplicate_fingerprint(
    image_bytes: bytes,
    parsed: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    parsed = parsed or {}

    brand = normalize_text(parsed.get("vyrobce"))
    model = normalize_text(parsed.get("model"))

    ocr_text = extract_watch_ocr_text(image_bytes)
    image_hash = compute_visual_hash(image_bytes)
    color_hash = compute_color_hash(image_bytes)
    subdial_count = detect_subdial_count(image_bytes)

    return {
        "version": DUPLICATE_VERSION,
        "brand": brand,
        "model": model,
        "ocr_text": ocr_text,
        "image_hash": image_hash,
        "color_hash": color_hash,
        "dominant_colors": [],
        "subdial_count": subdial_count,
        "debug": {
            "ocr_text": ocr_text,
            "hash_len": len(image_hash) if image_hash else 0,
            "color_hash_len": len(color_hash) if color_hash else 0,
            "subdial_count": subdial_count,
        },
    }


def compare_duplicate_fingerprints(
    new_fp: Dict[str, Any],
    old_fp: Dict[str, Any],
) -> Dict[str, Any]:
    score = 0
    reasons = []
    debug = {}

    visual_dist = bit_distance(
        new_fp.get("image_hash"),
        old_fp.get("image_hash"),
    )

    color_dist = color_distance(
        new_fp.get("color_hash"),
        old_fp.get("color_hash"),
    )

    ocr_sim = text_similarity(
        new_fp.get("ocr_text", ""),
        old_fp.get("ocr_text", ""),
    )

    new_brand = normalize_text(new_fp.get("brand"))
    old_brand = normalize_text(old_fp.get("brand"))

    new_model = normalize_text(new_fp.get("model"))
    old_model = normalize_text(old_fp.get("model"))

    new_subdial_count = new_fp.get("subdial_count")
    old_subdial_count = old_fp.get("subdial_count")

    debug["visual_distance"] = visual_dist
    debug["color_distance"] = color_dist
    debug["ocr_similarity"] = round(float(ocr_sim), 3)
    debug["new_brand"] = new_brand
    debug["old_brand"] = old_brand
    debug["new_model"] = new_model
    debug["old_model"] = old_model
    debug["new_subdial_count"] = new_subdial_count
    debug["old_subdial_count"] = old_subdial_count

    if visual_dist <= 45:
        score += 25
        reasons.append("visual_hash_very_close")
    elif visual_dist <= 90:
        score += 12
        reasons.append("visual_hash_close")

    if color_dist <= 0.18:
        score += 20
        reasons.append("color_very_close")
    elif color_dist <= 0.35:
        score += 10
        reasons.append("color_close")

    if ocr_sim >= 0.75:
        score += 30
        reasons.append("ocr_very_similar")
    elif ocr_sim >= 0.45:
        score += 15
        reasons.append("ocr_similar")

    if new_brand and old_brand:
        if new_brand == old_brand:
            score += 20
            reasons.append("same_brand")
        else:
            score -= 30
            reasons.append("different_brand")

    if new_model and old_model:
        if new_model == old_model:
            score += 35
            reasons.append("same_model")
        else:
            score -= 20
            reasons.append("different_model")

    if new_subdial_count is not None and old_subdial_count is not None:
        if int(new_subdial_count) == int(old_subdial_count):
            score += 15
            reasons.append("same_subdial_count")
        else:
            score -= 20
            reasons.append("different_subdial_count")

    # AUTOMATICKÉ ZAHOZENÍ JEN PŘI SKORO JISTÉ DUPLICITĚ
    same_subdial_count = (
        new_subdial_count is not None
        and old_subdial_count is not None
        and int(new_subdial_count) == int(old_subdial_count)
    )

    hard_visual_match = visual_dist <= 25
    hard_color_match = color_dist <= 0.12

    if (
        hard_visual_match
        and hard_color_match
        and same_subdial_count
        and score >= 110
    ):
        status = "duplicate"
    elif score >= 60:
        status = "possible_duplicate"
    else:
        status = "new"

    return {
        "score": int(score),
        "status": status,
        "reasons": reasons,
        "debug": debug,
    }