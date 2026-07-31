"""
template_ocr.py

Skeleton Pass extraction: runs OCR on the whole page and returns raw text plus a per-word
confidence score from Tesseract. This proves the OCR step works end-to-end. Depth Pass 3
replaces this with real anchor/label-based region extraction mapped to the field tables in
the project spec (Section 3) — the interface (a dict with 'status', 'fields', 'mean_confidence')
stays the same so downstream stages don't need to change.

Never crashes: OCR engine failures are caught and returned as a failed-status dict.
"""

from __future__ import annotations

import difflib
import logging
import os
import re

import numpy as np
import pytesseract
from pytesseract import Output

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure Tesseract path if specified in .env
if os.environ.get("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 60.0  # Tesseract confidence is 0-100
FUZZY_MATCH_THRESHOLD = 0.75  # tolerates small OCR noise, e.g. "NAME" misread as "MAME"
DIAGNOSIS_CODE_PATTERN = re.compile(r"[A-Z]\d{2}\.?\d{0,2}")

# Anchor-based field configs: each anchor is a sequence of tokens (punctuation-insensitive,
# fuzzy-matched to tolerate OCR noise) searched for in order (small gaps tolerated — see
# _find_anchor). max_width/x_slack bound how far the value is read from the anchor, since a
# claim form row often has another field's label starting shortly after — without this bound,
# extraction sweeps in unrelated text from the rest of the row (found via real testing).
CMS1500_FIELD_ANCHORS = {
    "patient_name": {"anchor": ["PATIENTS", "NAME"], "max_width": 530, "band_height": 45},
    # force_escalate=True: real testing across all 12 Group A claims showed only 25% accuracy
    # (3/12) for this field via anchor-based OCR — the narrow per-digit date boxes have far
    # more layout variance than the name field's single wide box, and band-tuning hit
    # diminishing returns. Rather than keep tuning pixel offsets, this field is always routed
    # to LLM escalation regardless of measured OCR confidence — a deliberate cost/accuracy
    # tradeoff decision, not an oversight.
    "patient_dob": {"anchor": ["PATIENTS", "BIRTH", "DATE"], "max_width": 260,
                     "band_height": 38, "top_offset": 12, "force_escalate": True},
    # force_escalate=True: real testing across all 12 Group A claims showed only 25% (3/12)
    # accuracy for this field — same pattern as patient_dob: numeric ID fields are more
    # OCR-error-prone than wide text fields (one failure was a genuine Tesseract digit-
    # insertion error, "990086221-00" misread as "1990086221-00", not a positioning bug).
    # Consistent rule emerging from testing: text-name fields suit cheap OCR; numeric/ID
    # fields are always escalated.
    "insured_id": {"anchor": ["INSUREDS", "ID", "NUMBER"], "max_width": 400, "band_height": 40,
                   "x_slack": 110, "force_escalate": True},
    # extraction_style="regex_codes": Box 21 holds up to 12 ICD-10-style codes in a grid, not
    # a single label-value pair — see _extract_diagnosis_codes. force_escalate=True: real
    # testing across all 12 Group A claims showed only 16.7% (2/12) accuracy with a
    # letter-sensitive scorer — this font systematically confuses "F" with "E", "L", and "G"
    # in these codes, and since the leading letter is clinically significant (F32 vs E32 are
    # different diagnoses), this is escalated rather than trusted, consistent with the pattern
    # for all other structured/coded fields tested so far.
    "diagnosis_codes": {"anchor": ["DIAGNOSIS", "OR", "NATURE"], "extraction_style": "regex_codes",
                         "force_escalate": True},
    # Box 24: Service lines - dates, procedure codes, charges (repeating rows)
    "service_lines": {"anchor": ["DATES", "OF", "SERVICE"], "extraction_style": "service_lines",
                       "band_height": 350, "force_escalate": True},
    # Box 28: Total charge (single value field)
    "total_charge": {"anchor": ["TOTAL", "CHARGE"], "max_width": 180, "band_height": 35},
}

# Both UB-04 fields are force-escalated: real testing across 3 different Group C samples
# showed the box-8 label-to-value gap varies wildly between scans (same-line on one page,
# ~260px below on another), so a fixed band sweeps in unrelated content from boxes in
# between rather than isolating the value. Same deliberate cost/accuracy tradeoff as
# patient_dob above — always escalate rather than trust an unreliable OCR-band read.
UB04_FIELD_ANCHORS = {
    "patient_name": {"anchor": ["PATIENT", "NAME"], "max_width": 560, "band_height": 40, "force_escalate": True},
    "patient_dob": {"anchor": ["BIRTHDATE"], "max_width": 260, "band_height": 40, "force_escalate": True},
    # Box 42-49: Revenue codes, descriptions, charges (repeating rows)
    "revenue_lines": {"anchor": ["REVENUE", "CODE"], "extraction_style": "revenue_lines",
                       "band_height": 400, "force_escalate": True},
    # Box 47: Total charges
    "total_charges": {"anchor": ["TOTALS"], "max_width": 180, "band_height": 35},
}

FIELD_ANCHORS_BY_FORM = {
    "CMS-1500": CMS1500_FIELD_ANCHORS,
    "UB-04": UB04_FIELD_ANCHORS,
}


def _normalize_token(t: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", t.upper())


def _fuzzy_token_match(a: str, b: str) -> bool:
    if a == b:
        return True
    if difflib.SequenceMatcher(None, a, b).ratio() >= FUZZY_MATCH_THRESHOLD:
        return True
    # OCR commonly confuses visually similar characters (I/L, O/0, S/5) in short label
    # tokens. Found necessary via real testing: "I.D." is frequently misread as "LD.",
    # which only scores 0.5 on plain character-similarity ratio — well below threshold —
    # despite being an unambiguous OCR error, not a genuinely different word.
    canonical = str.maketrans({"L": "I", "0": "O", "5": "S"})
    if a.translate(canonical) == b.translate(canonical):
        return True
    return difflib.SequenceMatcher(None, a.translate(canonical), b.translate(canonical)).ratio() >= FUZZY_MATCH_THRESHOLD


def _get_words(img: np.ndarray) -> list[dict]:
    """Word-level OCR with bounding boxes and timeout. Never raises — returns [] on failure."""
    try:
        data = pytesseract.image_to_data(img, output_type=Output.DICT, timeout=30)
    except Exception as exc:
        logger.error("Word-level OCR failed: %s", exc)
        return []

    words = []
    for text, left, top, width, height, conf in zip(
        data.get("text", []), data.get("left", []), data.get("top", []),
        data.get("width", []), data.get("height", []), data.get("conf", []),
    ):
        text = text.strip()
        if not text:
            continue
        try:
            conf_val = float(conf)
        except (TypeError, ValueError):
            conf_val = -1.0
        if conf_val < 0:
            continue
        words.append({"text": text, "left": left, "top": top, "width": width, "height": height, "conf": conf_val})
    return words


def _find_anchor(words: list[dict], anchor_tokens: list[str], max_gap: int = 1) -> dict | None:
    """
    Find all runs of words matching anchor_tokens in order, and return the topmost match
    (smallest 'top'). Tolerates up to max_gap extra/unmatched words between target tokens —
    found necessary via real testing: "I.D." on box 1a is frequently OCR'd as "LD.", which
    fails even fuzzy matching against "ID", so a strict consecutive-match requirement missed
    this anchor entirely. Real testing also showed Tesseract's word order isn't strictly
    top-to-bottom (it groups by block/column), so a label that legitimately repeats on the
    page (e.g. "INSURED'S" appears in boxes 1a, 4, 9, and 11) can have its intended earliest
    occurrence appear later in list order than a different box's occurrence — picking the
    topmost by pixel position is the semantically correct choice.
    """
    normalized = [_normalize_token(w["text"]) for w in words]
    target = [_normalize_token(t) for t in anchor_tokens]
    n, m = len(normalized), len(target)
    window = m + max_gap

    matches = []
    for i in range(n - window + 1):
        seg_positions = list(range(i, min(i + window, n)))
        matched_idx = []
        seg_pos = 0
        for tok in target:
            while seg_pos < len(seg_positions) and not _fuzzy_token_match(normalized[seg_positions[seg_pos]], tok):
                seg_pos += 1
            if seg_pos >= len(seg_positions):
                break
            matched_idx.append(seg_positions[seg_pos])
            seg_pos += 1
        if len(matched_idx) == m:
            span = [words[p] for p in matched_idx]
            matches.append({
                "left": min(w["left"] for w in span),
                "right": max(w["left"] + w["width"] for w in span),
                "bottom": max(w["top"] + w["height"] for w in span),
                "top": min(w["top"] for w in span),
            })

    if not matches:
        return None
    return min(matches, key=lambda mt: mt["top"])


def _read_value_below(words: list[dict], anchor_box: dict, band_height: int = 40,
                        x_slack: int = 40, max_width: int = 500, top_offset: int | None = None) -> tuple[str, float]:
    """
    Collect words in the band directly below an anchor, in reading order. Bounded on both
    left and right so it reads only this field's box, not the rest of the row (a bug found
    during real testing: without a right bound, this swept in unrelated later fields).

    top_offset, when given, measures the band start from the anchor's TOP instead of its
    BOTTOM — needed for fields like patient_dob where the label's measured glyph height is
    inflated (bold/serif digits reported ~28px tall vs ~14px for plain text), which makes a
    bottom-referenced band overlap the value instead of sitting below it (found via real
    testing: the DOB value physically sits within the label's own inflated bounding box).

    Never raises.
    """
    if top_offset is not None:
        band_top = anchor_box["top"] + top_offset
    else:
        band_top = anchor_box["bottom"] - 2
    band_bottom = band_top + band_height
    left_bound = anchor_box["left"] - x_slack
    right_bound = anchor_box["left"] + max_width

    candidates = [
        w for w in words
        if band_top <= w["top"] <= band_bottom and left_bound <= w["left"] <= right_bound
    ]
    candidates.sort(key=lambda w: (w["top"] // 10, w["left"]))  # reading order, tolerant of small row jitter

    if not candidates:
        return "", 0.0

    value_text = " ".join(w["text"] for w in candidates)
    mean_conf = sum(w["conf"] for w in candidates) / len(candidates)
    return value_text.strip(", "), round(mean_conf, 1)


def _extract_diagnosis_codes(words: list[dict], anchor_box: dict, right_offset: int = 850,
                               band_height: int = 115) -> tuple[list[str], float]:
    """
    Box 21 (CMS-1500) holds up to 12 ICD-10-style diagnosis codes in a 3-row x 4-column grid,
    not a single label-value pair — regex over the bounded region works better here than
    label-below-value extraction. Bounded to the left portion of the row (right_offset) since
    testing showed the same vertical band on the right side of the page holds unrelated Box 22
    content ("RESUBMISSION CODE ORIGINAL REF. NO.") that produces false-positive code matches
    if not excluded. 'O' is replaced with '0' before matching since ICD-10 codes don't use the
    letter O as a leading character, and OCR frequently confuses O/0 in this font. Never raises.
    """
    band_top = anchor_box["bottom"] - 2
    band_bottom = band_top + band_height
    right_bound = anchor_box["left"] + right_offset

    band_words = [w for w in words if band_top <= w["top"] <= band_bottom and w["left"] <= right_bound]
    band_words.sort(key=lambda w: (w["top"] // 10, w["left"]))

    if not band_words:
        return [], 0.0

    joined = "".join(w["text"] for w in band_words).replace("O", "0")
    codes = DIAGNOSIS_CODE_PATTERN.findall(joined)
    mean_conf = sum(w["conf"] for w in band_words) / len(band_words)
    return codes, round(mean_conf, 1)


def _extract_service_lines(words: list[dict], anchor_box: dict, band_height: int = 350) -> tuple[list[dict], float]:
    """
    CMS-1500 Box 24: Service lines with dates, place of service, CPT codes, charges.
    Uses position-based extraction for structured fields. Never raises.
    """
    band_top = anchor_box["bottom"] - 2
    band_bottom = band_top + band_height
    
    band_words = [w for w in words if band_top <= w["top"] <= band_bottom]
    if not band_words:
        return [], 0.0
    
    # Group words into rows (tolerance of 20px vertical variation)
    rows = []
    current_row = []
    current_y = None
    
    for w in sorted(band_words, key=lambda x: (x["top"], x["left"])):
        if current_y is None or abs(w["top"] - current_y) <= 20:
            current_row.append(w)
            current_y = w["top"] if current_y is None else current_y
        else:
            if current_row:
                rows.append(current_row)
            current_row = [w]
            current_y = w["top"]
    if current_row:
        rows.append(current_row)
    
    # Skip header rows (contain "FROM", "TO", "CHARGES", etc.)
    data_rows = []
    for row in rows:
        row_text = " ".join(w["text"] for w in row).upper()
        # Skip if row contains header keywords
        if any(kw in row_text for kw in ["FROM", "TO", "CHARGES", "SERVICE", "CPT/HCPCS", "MODIFIER", "POINTER"]):
            continue
        # Must have some numeric content (dates, charges, codes)
        if re.search(r"\d", row_text):
            data_rows.append(row)
    
    # Extract structured fields from each data row
    service_lines = []
    all_conf = []
    
    for row in data_rows:
        row_text = " ".join(w["text"] for w in row)
        
        # Extract dates - look for patterns like "07 16 25" or "07/16/25"
        # Common OCR patterns: spaces, slashes, hyphens between MM DD YY
        date_pattern = r"(\d{1,2})[\s\-/]+(\d{1,2})[\s\-/]+(\d{2,4})"
        date_matches = re.findall(date_pattern, row_text)
        
        if date_matches:
            # Format first date as MM/DD/YY
            m, d, y = date_matches[0]
            date_from = f"{m.zfill(2)}/{d.zfill(2)}/{y[-2:]}"
            # Second date if exists
            if len(date_matches) >= 2:
                m, d, y = date_matches[1]
                date_to = f"{m.zfill(2)}/{d.zfill(2)}/{y[-2:]}"
            else:
                date_to = date_from
        else:
            date_from = ""
            date_to = ""
        
        # Extract CPT code (5-digit code, typically 90000-99999)
        cpt_matches = re.findall(r"\b(9\d{4})\b", row_text)
        cpt_code = cpt_matches[0] if cpt_matches else ""
        
        # Extract charge (dollar amount, typically at end of row)
        charge_matches = re.findall(r"[\$]?(\d{1,4}\.\d{2})", row_text)
        charges = charge_matches[-1] if charge_matches else ""
        
        # Only add line if it has at least a CPT code or charge
        if cpt_code or charges:
            service_lines.append({
                "date_from": date_from,
                "date_to": date_to,
                "cpt_code": cpt_code,
                "charges": charges,
                "raw_text": row_text
            })
            all_conf.extend(w["conf"] for w in row)
    
    mean_conf = sum(all_conf) / len(all_conf) if all_conf else 0.0
    return service_lines, round(mean_conf, 1)


def _extract_revenue_lines(words: list[dict], anchor_box: dict, band_height: int = 400) -> tuple[list[dict], float]:
    """
    UB-04 Box 42-49: Revenue codes, descriptions, HCPCS, charges.
    Similar structure to service lines but with revenue codes. Never raises.
    """
    band_top = anchor_box["bottom"] - 2
    band_bottom = band_top + band_height
    
    band_words = [w for w in words if band_top <= w["top"] <= band_bottom]
    if not band_words:
        return [], 0.0
    
    # Group words into rows
    rows = []
    current_row = []
    current_y = None
    
    for w in sorted(band_words, key=lambda x: (x["top"], x["left"])):
        if current_y is None or abs(w["top"] - current_y) <= 15:
            current_row.append(w)
            current_y = w["top"] if current_y is None else current_y
        else:
            if current_row:
                rows.append(current_row)
            current_row = [w]
            current_y = w["top"]
    if current_row:
        rows.append(current_row)
    
    revenue_lines = []
    all_conf = []
    for row in rows:
        if len(row) < 2:
            continue
        line_data = {
            "revenue_code": "",
            "description": "",
            "charges": "",
            "raw_text": " ".join(w["text"] for w in row)
        }
        # Look for 4-digit revenue codes at start of line
        rev_codes = re.findall(r"\b\d{4}\b", line_data["raw_text"])
        if rev_codes:
            line_data["revenue_code"] = rev_codes[0]
        # Look for charge amounts
        charges = re.findall(r"\$?\d+\.\d{2}", line_data["raw_text"])
        if charges:
            line_data["charges"] = charges[-1]
        
        revenue_lines.append(line_data)
        all_conf.extend(w["conf"] for w in row)
    
    mean_conf = sum(all_conf) / len(all_conf) if all_conf else 0.0
    return revenue_lines, round(mean_conf, 1)


def extract_fields_by_anchor(img: np.ndarray, form_type: str) -> dict:
    """
    Depth Pass 3 extraction: locate each configured field's label anchor wherever OCR finds
    it, then read the value from the band directly below (or, for diagnosis_codes, regex-scan
    a bounded region), bounded to that field's box width. Never raises — a field that can't be
    located is reported with an empty value and zero confidence, not skipped silently and not
    a crash.
    """
    anchors = FIELD_ANCHORS_BY_FORM.get(form_type)
    if not anchors:
        return {"status": "ok", "stage": "extraction", "form_type": form_type,
                "fields": {}, "extraction_method": "anchor_based",
                "reason": f"no field anchor config for form_type '{form_type}'"}

    words = _get_words(img)
    if not words:
        return {"status": "failed", "stage": "extraction", "reason": "no OCR words detected"}

    fields = {}
    low_confidence_fields = []
    for field_name, config in anchors.items():
        anchor_box = _find_anchor(words, config["anchor"])
        if anchor_box is None:
            fields[field_name] = {"value": "", "confidence": 0.0, "found_anchor": False}
            low_confidence_fields.append({"word": field_name, "confidence": 0.0})
            continue

        if config.get("extraction_style") == "regex_codes":
            codes, conf = _extract_diagnosis_codes(words, anchor_box)
            fields[field_name] = {"value": codes, "confidence": conf, "found_anchor": True}
            if conf < LOW_CONFIDENCE_THRESHOLD or not codes or config.get("force_escalate"):
                low_confidence_fields.append({"word": field_name, "confidence": conf})
            continue
        
        if config.get("extraction_style") == "service_lines":
            lines, conf = _extract_service_lines(words, anchor_box, band_height=config.get("band_height", 350))
            fields[field_name] = {"value": lines, "confidence": conf, "found_anchor": True}
            if conf < LOW_CONFIDENCE_THRESHOLD or not lines or config.get("force_escalate"):
                low_confidence_fields.append({"word": field_name, "confidence": conf})
            continue
        
        if config.get("extraction_style") == "revenue_lines":
            lines, conf = _extract_revenue_lines(words, anchor_box, band_height=config.get("band_height", 400))
            fields[field_name] = {"value": lines, "confidence": conf, "found_anchor": True}
            if conf < LOW_CONFIDENCE_THRESHOLD or not lines or config.get("force_escalate"):
                low_confidence_fields.append({"word": field_name, "confidence": conf})
            continue

        value, conf = _read_value_below(
            words, anchor_box,
            band_height=config.get("band_height", 40),
            max_width=config.get("max_width", 500),
            top_offset=config.get("top_offset"),
            x_slack=config.get("x_slack", 40),
        )
        fields[field_name] = {"value": value, "confidence": conf, "found_anchor": True}
        if conf < LOW_CONFIDENCE_THRESHOLD or not value or config.get("force_escalate"):
            low_confidence_fields.append({"word": field_name, "confidence": conf})

    mean_conf = (
        sum(f["confidence"] for f in fields.values() if isinstance(f["confidence"], (int, float))) / len(fields)
        if fields else 0.0
    )

    return {
        "status": "ok",
        "stage": "extraction",
        "form_type": form_type,
        "fields": fields,
        "mean_confidence": round(mean_conf, 1),
        "low_confidence_words": low_confidence_fields,
        "extraction_method": "anchor_based",
    }


def extract_page(img: np.ndarray, form_type: str = "unknown") -> dict:
    """
    Run OCR across the whole page. Returns:
      {
        "status": "ok",
        "stage": "extraction",
        "form_type": ...,
        "raw_text": "...",
        "mean_confidence": float,
        "low_confidence_words": [...],   # words below threshold -> candidates for LLM escalation
      }
    """
    try:
        data = pytesseract.image_to_data(img, output_type=Output.DICT, timeout=30)
    except Exception as exc:
        logger.error("OCR extraction failed: %s", exc)
        return {"status": "failed", "stage": "extraction", "reason": str(exc)}

    words, confidences, low_conf_words = [], [], []
    for word, conf in zip(data.get("text", []), data.get("conf", [])):
        word = word.strip()
        if not word:
            continue
        try:
            conf_val = float(conf)
        except (TypeError, ValueError):
            continue
        if conf_val < 0:  # Tesseract uses -1 for non-text regions
            continue
        words.append(word)
        confidences.append(conf_val)
        if conf_val < LOW_CONFIDENCE_THRESHOLD:
            low_conf_words.append({"word": word, "confidence": conf_val})

    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "status": "ok",
        "stage": "extraction",
        "form_type": form_type,
        "raw_text": " ".join(words),
        "mean_confidence": round(mean_confidence, 1),
        "low_confidence_words": low_conf_words,
        "extraction_method": "template_ocr",
    }
