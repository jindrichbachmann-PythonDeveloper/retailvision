import base64
import io
import os

from openai import OpenAI


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1.5")


def ai_clean_watch_bytes(image_bytes: bytes) -> bytes:
    prompt = """
Remove any secondary, background, overlapping, duplicate or partially visible watches.
Keep only the main foreground watch.
Preserve the original main watch exactly.
Fill removed areas with clean black background.
"""

    img_file = io.BytesIO(image_bytes)
    img_file.name = "watch.png"

    result = client.images.edit(
        model=IMAGE_MODEL,
        image=img_file,
        prompt=prompt,
        size="1024x1024",
        output_format="png",
    )

    image_base64 = result.data[0].b64_json
    return base64.b64decode(image_base64)