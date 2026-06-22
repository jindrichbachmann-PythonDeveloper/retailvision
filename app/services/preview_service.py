import time
from typing import Dict, Any

from app.services.state_service import get_prev_state, cleanup_prev_states, iou_xyxy, ema_box
from app.services.yolo_service import yolo_detect_boxes
from app.services.split_service import split_objects_centered_v2

HOLD_SEC = 1.2
LOST_MAX = 10
MATCH_IOU = 0.25
EMA_ALPHA = 0.22

def _xywh_to_xyxy(box_xywh):
    x, y, w, h = box_xywh
    return (x, y, x + w, y + h)

async def detect_preview_logic(raw: bytes, session_id: str) -> Dict[str, Any]:
    if not raw:
        return {"ok": True, "held": False, "boxes": []}

    now = time.time()
    st = get_prev_state(session_id)

    if (now - float(st.get("cleanup_ts", 0.0))) > 30.0:
        cleanup_prev_states()
        st["cleanup_ts"] = now

    boxes = yolo_detect_boxes(raw)  # (x1,y1,x2,y2,conf,cls)

    # --- FALLBACK: když YOLO nic nenajde, zkus Hough split ---
    if not boxes:
        items = split_objects_centered_v2(raw)
        if items:
            best = items[0]  # už je sorted nejlepší první
            x1, y1, x2, y2 = _xywh_to_xyxy(best["box"])
            conf = float(best.get("score", 0.0)) / 10.0
            cls = -2  # značka "hough"
            boxes = [(x1, y1, x2, y2, conf, cls)]

    prev_box = st.get("box")
    best = None

    if boxes:
        if prev_box is not None:
            for (x1, y1, x2, y2, conf, cls) in boxes:
                if iou_xyxy(prev_box, (x1, y1, x2, y2)) >= MATCH_IOU:
                    best = ((x1, y1, x2, y2), conf, cls)
                    break

        if best is None:
            boxes = sorted(boxes, key=lambda b: b[4], reverse=True)
            x1, y1, x2, y2, conf, cls = boxes[0]
            best = ((x1, y1, x2, y2), conf, cls)

    if best is None:
        if (
            prev_box is not None
            and (now - float(st.get("ts", 0.0))) < HOLD_SEC
            and int(st.get("lost", 0)) < LOST_MAX
        ):
            st["lost"] += 1
            x1, y1, x2, y2 = prev_box
            return {"ok": True, "held": True, "boxes": [{"x1": x1, "y1": y1, "x2": x2, "y2": y2, "score": 0.01, "cls": -1}]}

        st["box"] = None
        st["lost"] = 0
        return {"ok": True, "held": False, "boxes": []}

    (x1, y1, x2, y2), conf, cls = best
    curr = (x1, y1, x2, y2)

    st["box"] = ema_box(st.get("box"), curr, alpha=EMA_ALPHA)
    st["ts"] = now
    st["lost"] = 0

    x1, y1, x2, y2 = st["box"]
    return {"ok": True, "held": False, "boxes": [{"x1": x1, "y1": y1, "x2": x2, "y2": y2, "score": float(conf), "cls": int(cls)}]}
