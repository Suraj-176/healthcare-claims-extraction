"""
page_classifier.py

Classifies a preprocessed page image into one of:
  - "tier_a_or_c"        : a real CMS-1500 or UB-04 claim form (grid layout detected)
  - "discard_attachment" : a tabular/EOB-style attachment page (Tier B, page 2+)
  - "reject_no_content"  : a separator/cover sheet with no claim data (Tier D reality)
  - "unknown_layout"     : none of the above matched confidently — routed to manual review,
                           never force-fit into a tier it doesn't match.

This is a Skeleton Pass classifier: it uses a fast, cheap whole-page OCR text sniff for
anchor keywords rather than a trained layout model. It is deliberately crude but real, and it
is designed to be replaced by a trained/anchor-based model in a later depth pass without
changing its interface.

Never crashes: OCR failures result in "unknown_layout", not an exception.
"""

from __future__ import annotations

import logging

import numpy as np
import pytesseract

logger = logging.getLogger(__name__)

CMS1500_KEYWORDS = ["HEALTH INSURANCE CLAIM FORM", "PICA", "NUCC"]

# Broadened based on real OCR failure analysis: on noisy/poor-quality scans, the literal
# "UB-04" text and "REV. CD" often don't survive OCR cleanly, but these other UB-04-specific
# box labels reliably do (verified against Group C pages 3 and 5, which failed to classify
# with the original narrower keyword list).
UB04_KEYWORDS = [
    "UB-04", "TYPE OF BILL", "REV. CD", "REV CD",
    "STATEMENT COVERS PERIOD", "OCCURRENCE SPAN", "CONDITION CODES",
]
SEPARATOR_KEYWORDS = ["DOCUMENT SEPARATOR", "USED TO SEPARATE EACH TRANSACTION"]
ATTACHMENT_KEYWORDS = ["TRACKING NO", "UNIQUE ID", "RECVDATE", "EXPLANATION OF BENEFITS", "EOB"]


def _sniff_text(img: np.ndarray) -> str:
    try:
        return pytesseract.image_to_string(img).upper()
    except Exception as exc:
        logger.warning("OCR text sniff failed during classification: %s", exc)
        return ""


def classify_page(img: np.ndarray) -> dict:
    """
    Classify one preprocessed page image. Never raises — always returns a status dict with a
    'tier' key, defaulting to 'unknown_layout' rather than a crash or a forced guess.
    """
    text = _sniff_text(img)
    if not text.strip():
        return {"status": "ok", "stage": "classification", "tier": "unknown_layout", "reason": "no text detected"}

    if any(k in text for k in SEPARATOR_KEYWORDS):
        return {"status": "ok", "stage": "classification", "tier": "reject_no_content",
                "reason": "separator/cover-sheet keywords found"}

    if any(k in text for k in CMS1500_KEYWORDS):
        return {"status": "ok", "stage": "classification", "tier": "tier_a", "form_type": "CMS-1500"}

    if any(k in text for k in UB04_KEYWORDS):
        return {"status": "ok", "stage": "classification", "tier": "tier_c", "form_type": "UB-04"}

    if any(k in text for k in ATTACHMENT_KEYWORDS):
        return {"status": "ok", "stage": "classification", "tier": "discard_attachment",
                "reason": "attachment/tracking-slip keywords found"}

    return {"status": "ok", "stage": "classification", "tier": "unknown_layout",
            "reason": "no known layout keywords matched"}
