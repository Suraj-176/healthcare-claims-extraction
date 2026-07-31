"""
image_prep.py

Loads a scanned claim page (TIFF) and applies basic deskew/denoise/binarize preprocessing
before OCR. Never crashes: any preprocessing failure falls back to the original image rather
than halting the pipeline.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def load_page(path: str) -> np.ndarray | None:
    """Load a page image as a grayscale numpy array. Returns None on failure (never raises)."""
    try:
        pil_img = Image.open(path)
        pil_img = pil_img.convert("L")  # grayscale
        return np.array(pil_img)
    except Exception as exc:
        logger.error("Failed to load image %s: %s", path, exc)
        return None


def deskew(img: np.ndarray) -> np.ndarray:
    """Estimate and correct small rotation angles. Falls back to the original on any failure."""
    try:
        inverted = 255 - img
        coords = np.column_stack(np.where(inverted > 0))
        if coords.shape[0] < 50:
            return img  # not enough foreground pixels to estimate angle reliably
        angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.1 or abs(angle) > 15:
            return img  # ignore negligible or implausibly large angles
        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
    except Exception as exc:
        logger.warning("Deskew failed, using original image: %s", exc)
        return img


def denoise_and_binarize(img: np.ndarray) -> np.ndarray:
    """Light denoise + adaptive threshold. Falls back to the original on any failure."""
    try:
        denoised = cv2.fastNlMeansDenoising(img, h=10)
        binary = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
        )
        return binary
    except Exception as exc:
        logger.warning("Denoise/binarize failed, using original image: %s", exc)
        return img


def preprocess_page(path: str) -> dict:
    """
    Full preprocessing pipeline for one page. Never raises — always returns a status dict.
    """
    img = load_page(path)
    if img is None:
        return {"status": "failed", "stage": "preprocessing", "reason": "could not load image"}

    deskewed = deskew(img)
    cleaned = denoise_and_binarize(deskewed)
    return {"status": "ok", "stage": "preprocessing", "image": cleaned}
