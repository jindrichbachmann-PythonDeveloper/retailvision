from typing import List, Dict, Any, Tuple
import cv2
import numpy as np


def variance_of_laplacian(g: np.ndarray) -> float:
    return cv2.Laplacian(g, cv2.CV_64F).var()


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0, x2 - x1), max(0, y2 - y1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = aw * ah + bw * bh - inter
    return inter / ua if ua > 0 else 0.0


def _box_center(box):
    x, y, w, h = box
    return x + w / 2.0, y + h / 2.0


def _same_watch_duplicate(a, b) -> bool:
    overlap = _iou(a["box"], b["box"])

    same_circle_position = False
    if "circle" in a and "circle" in b:
        axc, ayc, ar = a["circle"]
        bxc, byc, br = b["circle"]

        cdist = np.hypot(axc - bxc, ayc - byc)

        # duplicita = skoro stejná pozice ciferníku
        same_circle_position = cdist < max(35, min(ar, br) * 0.35)

    return overlap > 0.35 or same_circle_position


def _better_item(a, b):
    return (
        bool(a.get("valid", False)),
        float(a.get("area_ratio", 0.0)),
        float(a.get("score", 0.0)),
        float(a.get("sharp", 0.0)),
    ) >= (
        bool(b.get("valid", False)),
        float(b.get("area_ratio", 0.0)),
        float(b.get("score", 0.0)),
        float(b.get("sharp", 0.0)),
    )


def split_objects_centered_v2(image_bytes: bytes) -> List[Dict[str, Any]]:
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return []

        H, W = img.shape[:2]

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_eq = cv2.equalizeHist(gray)
        blur = cv2.GaussianBlur(gray_eq, (7, 7), 1.5)

        circles = cv2.HoughCircles(
            blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=90,
            param1=120,
            param2=36,
            minRadius=40,
            maxRadius=220,
        )
        if circles is None:
            return []

        circles = np.uint16(np.around(circles))[0, :]
        circles = sorted(circles, key=lambda c: c[2], reverse=True)

        filtered: List[Tuple[int, int, int]] = []
        for (x, y, r) in circles:
            x, y, r = int(x), int(y), int(r)

            is_duplicate = False

            for (fx, fy, fr) in filtered:
                dist = np.hypot(x - fx, y - fy)

                # duplicita = skoro stejná pozice ciferníku
                same_position = dist < max(35, min(r, fr) * 0.35)

                if same_position:
                    is_duplicate = True
                    break

            if not is_duplicate:
                filtered.append((x, y, r))

        out_items: List[Dict[str, Any]] = []

        H_MULT = 9.2
        W_MULT = 6.0
        CIRCLE_MARGIN = 6

        def _clamp(x: float, a: float, b: float) -> float:
            return a if x < a else (b if x > b else x)

        def _norm01(x: float, a: float, b: float) -> float:
            if b <= a:
                return 0.0
            return _clamp((x - a) / (b - a), 0.0, 1.0)

        for (x, y, r) in filtered:
            crop_h = int(r * H_MULT)
            crop_w = int(r * W_MULT)

            x1 = x - crop_w // 2
            y1 = y - crop_h // 2
            x2 = x + crop_w // 2
            y2 = y + crop_h // 2

            x1c = max(0, x1)
            y1c = max(0, y1)
            x2c = min(W, x2)
            y2c = min(H, y2)

            if (
                (x - r) < (x1c + CIRCLE_MARGIN) or
                (x + r) > (x2c - CIRCLE_MARGIN) or
                (y - r) < (y1c + CIRCLE_MARGIN) or
                (y + r) > (y2c - CIRCLE_MARGIN)
            ):
                continue

            crop = img[y1c:y2c, x1c:x2c]
            if crop.size == 0:
                continue

            g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            sharp = float(variance_of_laplacian(g))
            contrast = float(np.std(g))
            brightness = float(np.mean(g))

            bw = float(max(1, x2c - x1c))
            bh = float(max(1, y2c - y1c))
            area_ratio = (bw * bh) / float(max(1, W * H))

            valid = True
            if sharp < 25:
                valid = False
            if brightness < 20 or brightness > 240:
                valid = False

            s_sharp = _norm01(sharp, 20.0, 160.0)
            s_con = _norm01(contrast, 12.0, 110.0)
            s_bri_low = _norm01(brightness, 20.0, 70.0)
            s_bri_high = 1.0 - _norm01(brightness, 200.0, 245.0)
            s_bri = _clamp(min(s_bri_low, s_bri_high), 0.0, 1.0)
            s_size = _norm01(area_ratio, 0.010, 0.200)

            score01 = (
                0.45 * s_sharp +
                0.20 * s_con +
                0.20 * s_bri +
                0.15 * s_size
            )
            score10 = float(_clamp(score01 * 10.0, 0.0, 10.0))
            if score10 < 8.0:
                continue
            if score10 >= 7.0:
                tier = "TOP"
            elif score10 >= 4.0:
                tier = "OK"
            else:
                tier = "SLABE"

            ok, buf = cv2.imencode(".png", crop)
            if not ok:
                continue

            out_items.append({
                "bytes": buf.tobytes(),
                "sharp": sharp,
                "score": score10,
                "tier": tier,
                "valid": bool(valid),
                "brightness": brightness,
                "contrast": contrast,
                "area_ratio": float(area_ratio),
                "box": (int(x1c), int(y1c), int(x2c - x1c), int(y2c - y1c)),
                "circle": (int(x), int(y), int(r)),
            })

        if not out_items:
            return []

        out_items.sort(
            key=lambda it: (
                it["valid"],
                it["area_ratio"],
                it["score"],
                it["sharp"],
            ),
            reverse=True
        )

        final: List[Dict[str, Any]] = []

        for it in out_items:
            duplicate_found = False

            for jt in list(final):
                if _same_watch_duplicate(it, jt):
                    duplicate_found = True

                    if _better_item(it, jt):
                        try:
                            final.remove(jt)
                        except ValueError:
                            pass
                        final.append(it)

                    break

            if not duplicate_found:
                final.append(it)

        final.sort(
            key=lambda it: (
                it["valid"],
                it["area_ratio"],
                it["score"],
                it["sharp"],
            ),
            reverse=True
        )

        return final

    except Exception as e:
        print("split_objects_centered_v2 selhalo:", e)
        return []