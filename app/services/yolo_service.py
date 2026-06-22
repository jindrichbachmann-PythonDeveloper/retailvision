import os
from typing import List, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")
YOLO_CONF_TH = float(os.getenv("YOLO_CONF_TH", "0.25"))

_model = None

def get_yolo():
    global _model
    if _model is not None:
        return _model
    if not os.path.exists(YOLO_MODEL_PATH):
        return None
    _model = YOLO(YOLO_MODEL_PATH)
    return _model


def yolo_detect_boxes(raw: bytes) -> List[Tuple[int,int,int,int,float,int]]:
    """
    Returns: list of (x1,y1,x2,y2,conf,cls)
    """
    model = get_yolo()
    if model is None:
        return []

    nparr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    pred = model.predict(img, conf=YOLO_CONF_TH, verbose=False)[0]
    if pred.boxes is None:
        return []

    xyxy = pred.boxes.xyxy.cpu().numpy()
    confs = pred.boxes.conf.cpu().numpy()
    clss = pred.boxes.cls.cpu().numpy().astype(int)

    H, W = img.shape[:2]
    out = []
    for (x1, y1, x2, y2), sc, cl in zip(xyxy, confs, clss):
        x1 = max(0, min(int(x1), W - 1))
        y1 = max(0, min(int(y1), H - 1))
        x2 = max(0, min(int(x2), W))
        y2 = max(0, min(int(y2), H))
        if x2 <= x1 or y2 <= y1:
            continue
        out.append((x1, y1, x2, y2, float(sc), int(cl)))

    return out
