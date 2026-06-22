import time
from typing import Dict, Any, Optional, Tuple

PREV_STATES: Dict[str, Dict[str, Any]] = {}

def get_prev_state(session_id: str) -> Dict[str, Any]:
    st = PREV_STATES.get(session_id)
    if not st:
        st = {"box": None, "ts": 0.0, "lost": 0, "cleanup_ts": 0.0}
        PREV_STATES[session_id] = st
    return st

def cleanup_prev_states(max_idle_sec: float = 90.0, max_items: int = 500):
    now = time.time()
    dead = [sid for sid, st in PREV_STATES.items()
            if (now - float(st.get("ts", 0.0))) > max_idle_sec]
    for sid in dead:
        PREV_STATES.pop(sid, None)

    if len(PREV_STATES) > max_items:
        items = sorted(PREV_STATES.items(),
                       key=lambda kv: float(kv[1].get("ts", 0.0)))
        for sid, _ in items[: max(0, len(PREV_STATES) - max_items)]:
            PREV_STATES.pop(sid, None)

def iou_xyxy(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    x1, y1 = max(ax1, bx1), max(ay1, by1)
    x2, y2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, x2 - x1), max(0, y2 - y1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

def ema_box(prev: Optional[Tuple[int,int,int,int]],
            curr: Tuple[int,int,int,int],
            alpha: float = 0.22):
    if prev is None:
        return curr
    return tuple(int(round((1 - alpha) * p + alpha * c))
                 for p, c in zip(prev, curr))
