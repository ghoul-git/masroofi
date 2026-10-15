import cv2
import numpy as np
from django.conf import settings


def preprocess(image_path: str) -> np.ndarray:
    """Clean a receipt photo so OCR reads it faster and more accurately.

    Photos larger than settings.OCR_MAX_SIDE on their longest side are scaled down
    first: OCR time grows with the number of pixels. Smaller photos are not enlarged.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Could not read the image file.")

    height, width = image.shape[:2]
    scale = settings.OCR_MAX_SIDE / max(height, width)
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)
