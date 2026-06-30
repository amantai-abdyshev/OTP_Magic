import io
import logging

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_detector = cv2.QRCodeDetector()


def decode_qr(img_bytes: bytes) -> list[str]:
    """Decode QR codes from raw image bytes. Returns [] if none found."""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.load()
        img = img.convert("RGB")
        if max(img.size) > 1920:
            img.thumbnail((1920, 1920), Image.LANCZOS)

        arr = np.array(img)
        data, _, _ = _detector.detectAndDecode(arr)
        if data:
            return [data]
        return []
    except Exception as exc:
        logger.warning("QR decode error: %s", exc)
        return []
