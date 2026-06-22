import io
import cv2
import numpy as np
from PIL import Image, ImageEnhance
import pytesseract


def decode_image(raw: bytes) -> np.ndarray:
    nparr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def enhance_image(b: bytes) -> bytes:
    # 1:1 z monolitu (bez AI/rembg)
    try:
        img = Image.open(io.BytesIO(b)).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.10)
        buf = io.BytesIO()
        img.save(buf, format="PNG", quality=95)
        return buf.getvalue()
    except Exception as e:
        print("enhance_image:", e)
        return b


def try_ocr(image_bytes: bytes) -> str:
    # 1:1 z monolitu
    try:
        pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return pytesseract.image_to_string(pil, lang="ces+eng").strip()
    except Exception as e:
        print("OCR fail:", e)
        return ""
