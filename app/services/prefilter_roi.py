# app/services/prefilter_roi.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import cv2
import numpy as np


@dataclass
class PrefilterConfig:
    # Kolik plochy má zabírat "hlavní objekt" (odhad přes hrany/kontrast) – hrubý sanity check
    min_area_ratio: float = 0.01
    max_area_ratio: float = 0.98

    # Rozmazání: čím vyšší, tím ostřejší; pod limitem vyhazujeme
    min_laplacian_var: float = 60.0

    # Kontrast/obsah: pod limitem vyhazujeme (tmavá/šedá fotka bez detailu)
    min_std_gray: float = 18.0

    # Expozice: pokud je skoro vše černé nebo skoro vše bílé, vyhazujeme
    dark_mean_threshold: float = 25.0
    bright_mean_threshold: float = 235.0


def _to_gray(img_bgr: np.ndarray) -> np.ndarray:
    if img_bgr is None:
        raise ValueError("img_bgr is None")
    if img_bgr.ndim == 2:
        return img_bgr
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


def prefilter_watch_geometry(
    img_bgr: np.ndarray,
    *,
    min_area_ratio: float = 0.01,
    max_area_ratio: float = 0.98,
    debug: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Geometricko-kvalitativní prefilter pro fotku hodinek.
    Cíl: rychle zahodit očividné odpady (rozmazané, tmavé, přepálené, bez detailu),
    než se pustí dražší AI kontrola.

    Vrací: (ok, info)
    """
    cfg = PrefilterConfig(
        min_area_ratio=min_area_ratio,
        max_area_ratio=max_area_ratio,
    )

    info: Dict[str, Any] = {"ok": True, "reasons": []}

    gray = _to_gray(img_bgr)

    h, w = gray.shape[:2]
    if h < 64 or w < 64:
        info["ok"] = False
        info["reasons"].append("image_too_small")
        return False, info

    mean = float(np.mean(gray))
    std = float(np.std(gray))
    info["mean_gray"] = mean
    info["std_gray"] = std

    if mean <= cfg.dark_mean_threshold:
        info["ok"] = False
        info["reasons"].append("too_dark")
        return False, info

    if mean >= cfg.bright_mean_threshold:
        info["ok"] = False
        info["reasons"].append("too_bright")
        return False, info

    if std < cfg.min_std_gray:
        info["ok"] = False
        info["reasons"].append("low_contrast_or_flat")
        return False, info

    # Rozmazání – Laplacian variance
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    lap_var = float(lap.var())
    info["laplacian_var"] = lap_var
    if lap_var < cfg.min_laplacian_var:
        info["ok"] = False
        info["reasons"].append("blurry")
        return False, info

    # Hrubý odhad "obsahu"/objektu přes hrany
    edges = cv2.Canny(gray, 60, 160)
    edge_ratio = float(np.count_nonzero(edges)) / float(h * w)
    info["edge_ratio"] = edge_ratio

    # Pokud nejsou skoro žádné hrany, je to podezřelé (rozmazané/šedé)
    if edge_ratio < 0.002:
        info["ok"] = False
        info["reasons"].append("too_little_detail")
        return False, info

    # Přibližná plocha "aktivních" oblastí (dilatované hrany)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dil = cv2.dilate(edges, k, iterations=2)
    active = float(np.count_nonzero(dil)) / float(h * w)
    info["active_area_ratio"] = active

    if active < cfg.min_area_ratio:
        info["ok"] = False
        info["reasons"].append("object_too_small_or_empty")
        return False, info

    if active > cfg.max_area_ratio:
        info["ok"] = False
        info["reasons"].append("object_too_large_or_crop_too_tight")
        return False, info

    return True, info