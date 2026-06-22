from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import io

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.services.ai_cleanup_service import ai_clean_watch_bytes
from app.services.duplicate_service import build_duplicate_fingerprint


DEBUG_DIR = Path(r"C:\Users\jindr\OneDrive\Desktop\porovnani")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

AI_ATTEMPTS = 3

DIAL_SIZE = 420

MIN_FINAL_SCORE = 70
MIN_COLOR_SCORE = 35
MIN_EDGE_SCORE = 80


def _next_compare_number() -> int:
    existing = list(DEBUG_DIR.glob("hodinky_*_compare.jpg"))
    return len(existing) + 1


def _bytes_to_pil_rgb(image_bytes: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(image_bytes))
    return image.convert("RGB")


def _pil_to_bytes(image: Image.Image, fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _bytes_to_cv_bgr(image_bytes: bytes) -> np.ndarray:
    pil_img = _bytes_to_pil_rgb(image_bytes)
    arr = np.array(pil_img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _cv_bgr_to_pil_rgb(img_bgr: np.ndarray) -> Image.Image:
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(img_rgb)


def _resize_for_panel(image: Image.Image, panel_w: int, panel_h: int) -> Image.Image:
    image = image.copy()
    image.thumbnail((panel_w, panel_h))

    canvas = Image.new("RGB", (panel_w, panel_h), "white")
    x = (panel_w - image.width) // 2
    y = (panel_h - image.height) // 2

    canvas.paste(image, (x, y))
    return canvas


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box_x: int,
    box_y: int,
    box_w: int,
    box_h: int,
    font: ImageFont.ImageFont,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)

    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = box_x + (box_w - text_w) // 2
    y = box_y + (box_h - text_h) // 2

    draw.text((x, y), text, fill="black", font=font)


def _find_huge_circle(img_bgr: np.ndarray) -> Optional[Tuple[int, int, int]]:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)

    h, w = gray.shape[:2]
    min_dim = min(w, h)

    min_radius = int(min_dim * 0.18)
    max_radius = int(min_dim * 0.48)

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=int(min_dim * 0.3),
        param1=80,
        param2=28,
        minRadius=min_radius,
        maxRadius=max_radius,
    )

    if circles is None:
        return None

    circles = np.round(circles[0, :]).astype("int")

    image_center_x = w // 2
    image_center_y = h // 2

    best_circle = None
    best_score = -999999

    for x, y, r in circles:
        center_dist = ((x - image_center_x) ** 2 + (y - image_center_y) ** 2) ** 0.5
        score = (r * 3) - (center_dist * 0.7)

        if score > best_score:
            best_score = score
            best_circle = (x, y, r)

    return best_circle


def _crop_circle_square(
    img_bgr: np.ndarray,
    circle: Tuple[int, int, int],
    padding: float = 1.18,
) -> np.ndarray:
    x, y, r = circle
    h, w = img_bgr.shape[:2]

    rr = int(r * padding)

    x1 = max(0, x - rr)
    y1 = max(0, y - rr)
    x2 = min(w, x + rr)
    y2 = min(h, y + rr)

    return img_bgr[y1:y2, x1:x2].copy()


def _normalize_dial(dial_bgr: np.ndarray) -> np.ndarray:
    return cv2.resize(
        dial_bgr,
        (DIAL_SIZE, DIAL_SIZE),
        interpolation=cv2.INTER_AREA,
    )


def extract_huge_circle_dial(image_bytes: bytes) -> Dict[str, Any]:
    img_bgr = _bytes_to_cv_bgr(image_bytes)

    circle = _find_huge_circle(img_bgr)

    if circle is None:
        return {
            "ok": False,
            "reason": "huge_circle_not_found",
            "dial_bytes": None,
            "circle": None,
        }

    dial_bgr = _crop_circle_square(img_bgr, circle)
    dial_bgr = _normalize_dial(dial_bgr)

    dial_pil = _cv_bgr_to_pil_rgb(dial_bgr)
    dial_bytes = _pil_to_bytes(dial_pil)

    return {
        "ok": True,
        "reason": "huge_circle_found",
        "dial_bytes": dial_bytes,
        "circle": circle,
    }


def _gray_score(original_bgr: np.ndarray, ai_bgr: np.ndarray) -> int:
    original_gray = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2GRAY)
    ai_gray = cv2.cvtColor(ai_bgr, cv2.COLOR_BGR2GRAY)

    diff = cv2.absdiff(original_gray, ai_gray)
    mean_diff = float(np.mean(diff))

    score = 100 - int(mean_diff / 2.2)
    return max(0, min(100, score))


def _edge_score(original_bgr: np.ndarray, ai_bgr: np.ndarray) -> int:
    original_gray = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2GRAY)
    ai_gray = cv2.cvtColor(ai_bgr, cv2.COLOR_BGR2GRAY)

    original_edges = cv2.Canny(original_gray, 60, 160)
    ai_edges = cv2.Canny(ai_gray, 60, 160)

    diff = cv2.absdiff(original_edges, ai_edges)
    mean_diff = float(np.mean(diff))

    score = 100 - int(mean_diff / 2.0)
    return max(0, min(100, score))


def _color_score_rgb(original_bgr: np.ndarray, ai_bgr: np.ndarray) -> int:
    original_rgb = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2RGB)
    ai_rgb = cv2.cvtColor(ai_bgr, cv2.COLOR_BGR2RGB)

    diff = cv2.absdiff(original_rgb, ai_rgb)
    mean_diff = float(np.mean(diff))

    score = 100 - int(mean_diff / 2.0)
    return max(0, min(100, score))


def _color_score_hsv(original_bgr: np.ndarray, ai_bgr: np.ndarray) -> int:
    original_hsv = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2HSV)
    ai_hsv = cv2.cvtColor(ai_bgr, cv2.COLOR_BGR2HSV)

    original_h = original_hsv[:, :, 0].astype(np.int16)
    ai_h = ai_hsv[:, :, 0].astype(np.int16)

    hue_diff = np.abs(original_h - ai_h)
    hue_diff = np.minimum(hue_diff, 180 - hue_diff)

    sat_diff = cv2.absdiff(original_hsv[:, :, 1], ai_hsv[:, :, 1])
    val_diff = cv2.absdiff(original_hsv[:, :, 2], ai_hsv[:, :, 2])

    hue_mean = float(np.mean(hue_diff))
    sat_mean = float(np.mean(sat_diff))
    val_mean = float(np.mean(val_diff))

    penalty = (hue_mean * 1.2) + (sat_mean * 0.25) + (val_mean * 0.15)

    score = 100 - int(penalty)
    return max(0, min(100, score))


def _combined_color_score(original_bgr: np.ndarray, ai_bgr: np.ndarray) -> int:
    rgb_score = _color_score_rgb(original_bgr, ai_bgr)
    hsv_score = _color_score_hsv(original_bgr, ai_bgr)

    final = int((rgb_score * 0.45) + (hsv_score * 0.55))
    return max(0, min(100, final))


def compare_dial_identity(
    original_dial_bytes: bytes,
    ai_dial_bytes: bytes,
) -> Dict[str, Any]:
    original_bgr = _bytes_to_cv_bgr(original_dial_bytes)
    ai_bgr = _bytes_to_cv_bgr(ai_dial_bytes)

    if original_bgr.shape != ai_bgr.shape:
        ai_bgr = cv2.resize(
            ai_bgr,
            (original_bgr.shape[1], original_bgr.shape[0]),
            interpolation=cv2.INTER_AREA,
        )

    gray_score = _gray_score(original_bgr, ai_bgr)
    edge_score = _edge_score(original_bgr, ai_bgr)
    color_score = _combined_color_score(original_bgr, ai_bgr)

    final_score = int(
        (gray_score * 0.30)
        + (edge_score * 0.50)
        + (color_score * 0.15)
    )

    ok = (
        final_score >= MIN_FINAL_SCORE
        and color_score >= MIN_COLOR_SCORE
        and edge_score >= MIN_EDGE_SCORE
    )

    return {
        "ok": ok,
        "score": final_score,
        "gray_score": gray_score,
        "edge_score": edge_score,
        "color_score": color_score,
        "min_final_score": MIN_FINAL_SCORE,
        "min_color_score": MIN_COLOR_SCORE,
        "min_edge_score": MIN_EDGE_SCORE,
    }


def _get_subdial_count(fp: Dict[str, Any]) -> int:
    value = fp.get("subdial_count")

    if value is None:
        value = fp.get("subdials_count")

    if value is None:
        value = fp.get("detected_subdials")

    if value is None:
        return -1

    try:
        return int(value)
    except Exception:
        return -1


def _subdial_identity_ok(
    original_fp: Dict[str, Any],
    ai_fp: Dict[str, Any],
) -> Dict[str, Any]:
    original_subdials = _get_subdial_count(original_fp)
    ai_subdials = _get_subdial_count(ai_fp)

    ok = (
        original_subdials >= 0
        and ai_subdials >= 0
        and original_subdials == ai_subdials
    )

    return {
        "ok": ok,
        "original_subdials": original_subdials,
        "ai_subdials": ai_subdials,
    }


def _check_ai_result_against_original(
    original_dial_bytes: bytes,
    ai_image_bytes: bytes,
) -> Dict[str, Any]:

    ai_dial = extract_huge_circle_dial(ai_image_bytes)

    if not ai_dial["ok"]:
        return {
            "ok": False,
            "reason": "ai_huge_circle_not_found",
            "score": 0,
            "watch_identity_ok": False,
            "subdial_identity_ok": False,
            "image": ai_image_bytes,
            "original_dial": original_dial_bytes,
            "ai_dial": None,
        }

    dial_compare = compare_dial_identity(
        original_dial_bytes=original_dial_bytes,
        ai_dial_bytes=ai_dial["dial_bytes"],
    )

    original_fp = build_duplicate_fingerprint(
        original_dial_bytes,
        {"vyrobce": None, "model": None},
    )

    ai_fp = build_duplicate_fingerprint(
        ai_dial["dial_bytes"],
        {"vyrobce": None, "model": None},
    )

    subdial_identity = _subdial_identity_ok(
        original_fp=original_fp,
        ai_fp=ai_fp,
    )

    ok = (
        dial_compare["ok"] is True
        and subdial_identity["ok"] is True
    )

    return {
        "ok": ok,
        "reason": "same_dial_confirmed" if ok else "dial_color_shape_or_subdials_changed",
        "score": dial_compare["score"],
        "watch_identity_ok": dial_compare["ok"],
        "subdial_identity_ok": subdial_identity["ok"],
        "dial_compare": dial_compare,
        "subdial_identity": subdial_identity,
        "image": ai_image_bytes,
        "original_dial": original_dial_bytes,
        "ai_dial": ai_dial["dial_bytes"],
    }


def _make_compare_collage(
    original_bytes: bytes,
    original_dial_bytes: Optional[bytes],
    ai_results: List[Dict[str, Any]],
    final_ok: bool,
    best_attempt: Optional[int],
    reason: str,
) -> Path:
    compare_number = _next_compare_number()

    panel_w = 300
    panel_h = 380
    header_h = 45
    footer_h = 110

    panels: List[Dict[str, Any]] = []

    panels.append({
        "title": "ORIGINAL",
        "image": original_bytes,
        "footer": "vstupni crop po rembg",
    })

    panels.append({
        "title": "ORIGINAL DIAL",
        "image": original_dial_bytes,
        "footer": "huge circle originalu",
    })

    for attempt in range(1, AI_ATTEMPTS + 1):
        found = None

        for item in ai_results:
            if item.get("attempt") == attempt:
                found = item
                break

        if found is None:
            panels.append({
                "title": f"AI #{attempt}",
                "image": None,
                "footer": "missing attempt",
            })

            panels.append({
                "title": f"AI #{attempt} DIAL",
                "image": None,
                "footer": "missing dial",
            })

            continue

        title = f"AI #{attempt}"

        if best_attempt is not None and attempt == best_attempt:
            title += " BEST"

        dial_compare = found.get("dial_compare") or {}

        panels.append({
            "title": title,
            "image": found.get("image"),
            "footer": (
                f"ok={found.get('ok')} | "
                f"score={found.get('score')} | "
                f"same={found.get('watch_identity_ok')} | "
                f"sub={found.get('subdial_identity_ok')}"
            ),
        })

        panels.append({
            "title": f"AI #{attempt} DIAL",
            "image": found.get("ai_dial"),
            "footer": (
                f"gray={dial_compare.get('gray_score')} | "
                f"edge={dial_compare.get('edge_score')} | "
                f"color={dial_compare.get('color_score')}"
            ),
        })

    columns = len(panels)

    collage_w = panel_w * columns
    collage_h = header_h + panel_h + footer_h + 30

    collage = Image.new("RGB", (collage_w, collage_h), "white")
    draw = ImageDraw.Draw(collage)
    font = ImageFont.load_default()

    for index, panel in enumerate(panels):
        x = index * panel_w

        draw.rectangle(
            [x, 0, x + panel_w - 1, collage_h - 1],
            outline="black",
            width=2,
        )

        _draw_centered_text(
            draw=draw,
            text=panel["title"],
            box_x=x,
            box_y=0,
            box_w=panel_w,
            box_h=header_h,
            font=font,
        )

        image_bytes = panel.get("image")

        if image_bytes:
            try:
                img = _bytes_to_pil_rgb(image_bytes)
                img_panel = _resize_for_panel(img, panel_w, panel_h)
                collage.paste(img_panel, (x, header_h))
            except Exception as e:
                _draw_centered_text(
                    draw=draw,
                    text=f"IMAGE ERROR: {repr(e)}",
                    box_x=x,
                    box_y=header_h,
                    box_w=panel_w,
                    box_h=panel_h,
                    font=font,
                )
        else:
            _draw_centered_text(
                draw=draw,
                text="NO IMAGE",
                box_x=x,
                box_y=header_h,
                box_w=panel_w,
                box_h=panel_h,
                font=font,
            )

        footer_y = header_h + panel_h

        draw.multiline_text(
            (x + 10, footer_y + 10),
            str(panel.get("footer") or ""),
            fill="black",
            font=font,
            spacing=4,
        )

    final_text = f"FINAL ok={final_ok} | reason={reason}"
    draw.text((10, collage_h - 22), final_text, fill="black", font=font)

    output_path = DEBUG_DIR / f"hodinky_{compare_number:03d}_compare.jpg"
    collage.save(output_path, quality=92)

    print(f"🖼️ Uloženo vizuální porovnání: {output_path}")

    return output_path


def clean_watch_identity_guard_best_of_three(
    original_bytes: bytes,
) -> Dict[str, Any]:

    if not original_bytes:
        return {
            "ok": False,
            "reason": "missing_original_image",
            "image": None,
            "attempts": [],
        }

    original_dial_result = extract_huge_circle_dial(original_bytes)

    if not original_dial_result.get("ok"):
        compare_path = _make_compare_collage(
            original_bytes=original_bytes,
            original_dial_bytes=None,
            ai_results=[],
            final_ok=False,
            best_attempt=None,
            reason="original_huge_circle_not_found_ai_not_started",
        )

        print("❌ AI same watch guard: originál nemá huge circle, AI clean se nespouští")

        return {
            "ok": False,
            "reason": "original_huge_circle_not_found_ai_not_started",
            "image": None,
            "attempts": [],
            "compare_path": str(compare_path),
        }

    original_dial_bytes = original_dial_result["dial_bytes"]

    valid_results: List[Dict[str, Any]] = []
    all_attempts: List[Dict[str, Any]] = []

    for attempt_number in range(1, AI_ATTEMPTS + 1):
        try:
            ai_image = ai_clean_watch_bytes(original_bytes)

            if not ai_image:
                raise ValueError("ai_clean_watch_bytes returned empty image")

            checked = _check_ai_result_against_original(
                original_dial_bytes=original_dial_bytes,
                ai_image_bytes=ai_image,
            )

            score = int(checked.get("score") or 0)

            attempt_info = {
                "attempt": attempt_number,
                "ok": checked["ok"],
                "score": score,
                "watch_identity_ok": checked["watch_identity_ok"],
                "subdial_identity_ok": checked["subdial_identity_ok"],
                "dial_compare": checked.get("dial_compare"),
                "subdial_identity": checked.get("subdial_identity"),
                "image": checked["image"],
                "original_dial": checked.get("original_dial"),
                "ai_dial": checked.get("ai_dial"),
                "reason": checked.get("reason"),
            }

            all_attempts.append(attempt_info)

            dial_compare = checked.get("dial_compare") or {}

            print(
                f"\n"
                f"🧪 AI same watch guard pokus #{attempt_number}\n"
                f"score={score}\n"
                f"gray={dial_compare.get('gray_score')}\n"
                f"edge={dial_compare.get('edge_score')}\n"
                f"color={dial_compare.get('color_score')}\n"
                f"same_watch={checked['watch_identity_ok']}\n"
                f"same_subdials={checked['subdial_identity_ok']}\n"
                f"ok={checked['ok']}\n"
                f"reason={checked.get('reason')}\n"
            )

            if checked["ok"]:
                valid_results.append(attempt_info)

        except Exception as e:
            print(f"❌ AI same watch guard pokus #{attempt_number} selhal:", repr(e))

            all_attempts.append({
                "attempt": attempt_number,
                "ok": False,
                "score": 0,
                "watch_identity_ok": False,
                "subdial_identity_ok": False,
                "error": repr(e),
                "image": None,
                "original_dial": original_dial_bytes,
                "ai_dial": None,
            })

    if not valid_results:
        compare_path = _make_compare_collage(
            original_bytes=original_bytes,
            original_dial_bytes=original_dial_bytes,
            ai_results=all_attempts,
            final_ok=False,
            best_attempt=None,
            reason="ai_changed_dial_color_shape_or_subdials",
        )

        return {
            "ok": False,
            "reason": "ai_changed_dial_color_shape_or_subdials",
            "image": None,
            "attempts": all_attempts,
            "compare_path": str(compare_path),
        }

    best = max(
        valid_results,
        key=lambda item: int(item.get("score") or 0),
    )

    compare_path = _make_compare_collage(
        original_bytes=original_bytes,
        original_dial_bytes=original_dial_bytes,
        ai_results=all_attempts,
        final_ok=True,
        best_attempt=best["attempt"],
        reason="same_dial_color_shape_and_subdials_confirmed",
    )

    return {
        "ok": True,
        "reason": "same_dial_color_shape_and_subdials_confirmed",
        "image": best["image"],
        "attempt": best["attempt"],
        "score": best["score"],
        "dial_compare": best.get("dial_compare"),
        "subdial_identity": best.get("subdial_identity"),
        "attempts": all_attempts,
        "compare_path": str(compare_path),
    }