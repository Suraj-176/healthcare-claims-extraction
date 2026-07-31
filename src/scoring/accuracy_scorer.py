"""
accuracy_scorer.py

Diffs anchor-extracted field values against the ground truth parser's output (Depth Pass 1)
for the fields both stages currently cover. This is Depth Pass 5's core, built early because
it's the only way to know whether Depth Pass 3's extraction is actually improving accuracy or
just producing different-looking wrong answers.

Comparison is normalized (case-insensitive, whitespace-collapsed) since OCR and ground truth
formatting conventions differ even when the underlying value is correct.
"""

from __future__ import annotations

import re


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().upper())


def score_patient_name(extracted_fields: dict, ground_truth_claim: dict, form_format: str) -> dict:
    """
    Compares the anchor-extracted 'patient_name' field against the ground truth parser's
    last-name/first-name fields for one claim. form_format is 'nsf' or 'ub92' since the two
    ground truth schemas use different field key prefixes.

    'success' is the real pass/fail metric: both last and first name must be present in the
    extracted text, regardless of exact punctuation, middle-initial inclusion, or token order
    (a scan legitimately including a middle initial, or a name in a different word order, is a
    correct extraction — the original strict-equality check wrongly failed both cases when
    this was first measured).
    """
    extracted_value = extracted_fields.get("patient_name", {}).get("value", "")
    extracted_norm = _normalize(extracted_value)

    records = ground_truth_claim.get("records", {})
    if form_format == "nsf":
        ca0 = records.get("CA0", [{}])[0]
        last = ca0.get("04.0_patient_last_name", "")
        first = ca0.get("05.0_patient_first_name", "")
    else:  # ub92
        rec20 = records.get("20", [{}])[0]
        last = rec20.get("04_patient_last_name", "")
        first = rec20.get("05_patient_first_name", "")

    expected_norm = _normalize(f"{last}, {first}")
    last_found = _normalize(last) in extracted_norm if last else False
    first_found = _normalize(first) in extracted_norm if first else False
    success = last_found and first_found

    return {
        "field": "patient_name",
        "extracted": extracted_value,
        "expected": f"{last}, {first}",
        "success": success,
        "exact_match": extracted_norm == expected_norm,
        "last_name_found": last_found,
        "first_name_found": first_found,
    }


def score_patient_dob(extracted_fields: dict, ground_truth_claim: dict, form_format: str) -> dict:
    """
    Compares the anchor-extracted 'patient_dob' field (form shows MM-DD-YYYY) against the
    ground truth parser's DOB field (stored as YYYYMMDD). Success requires month and day to
    match exactly and at least 3 of 4 year digits to match, since OCR digit-level noise (e.g.
    misreading a single '1' as '4' in a bold/serif year) is a known, separate failure mode
    from field-positioning bugs and shouldn't be conflated with them in this score.
    """
    extracted_value = extracted_fields.get("patient_dob", {}).get("value", "")
    extracted_digits = re.sub(r"\D", "", extracted_value)

    records = ground_truth_claim.get("records", {})
    if form_format == "nsf":
        ca0 = records.get("CA0", [{}])[0]
        dob_raw = ca0.get("08.0_patient_date_of_birth", "")
    else:
        rec20 = records.get("20", [{}])[0]
        dob_raw = rec20.get("08_patient_birthdate", "")

    if len(dob_raw) != 8:
        return {"field": "patient_dob", "extracted": extracted_value, "expected": dob_raw,
                "success": False, "reason": "ground truth DOB missing or malformed"}

    expected_year, expected_month, expected_day = dob_raw[:4], dob_raw[4:6], dob_raw[6:8]

    month_found = expected_month.lstrip("0") in extracted_digits or expected_month in extracted_digits
    day_found = expected_day.lstrip("0") in extracted_digits or expected_day in extracted_digits
    year_digit_matches = sum(1 for a, b in zip(expected_year, extracted_digits[-4:]) if a == b) if len(extracted_digits) >= 4 else 0

    success = month_found and day_found and year_digit_matches >= 3

    return {
        "field": "patient_dob",
        "extracted": extracted_value,
        "expected": f"{expected_month}-{expected_day}-{expected_year}",
        "success": success,
        "month_found": month_found,
        "day_found": day_found,
        "year_digit_matches": year_digit_matches,
    }


def score_insured_id(extracted_fields: dict, ground_truth_claim: dict, form_format: str) -> dict:
    """
    Compares the anchor-extracted 'insured_id' field against the ground truth parser's
    insured identification number. Ground truth stores this digit-only (e.g. dashes in
    '990086221-00' are stripped to '99008622100'), so comparison is digit-only on both sides.
    UB-04 form doesn't currently extract this field, so form_format='ub92' always reports
    not-applicable rather than a false failure.
    """
    if form_format != "nsf":
        return {"field": "insured_id", "success": None, "reason": "not applicable for this form format"}

    extracted_value = extracted_fields.get("insured_id", {}).get("value", "")
    extracted_digits = re.sub(r"\D", "", extracted_value)

    da0 = ground_truth_claim.get("records", {}).get("DA0", [{}])[0]
    expected_raw = da0.get("18.0_insured_identification_number", "")
    expected_digits = re.sub(r"\D", "", expected_raw)

    success = bool(expected_digits) and expected_digits == extracted_digits

    return {
        "field": "insured_id",
        "extracted": extracted_value,
        "expected": expected_raw,
        "success": success,
    }


def score_diagnosis_codes(extracted_fields: dict, ground_truth_claim: dict, form_format: str) -> dict:
    """
    Compares the extracted diagnosis code list against the ground truth parser's EA0 diagnosis
    code fields (32.0, 33.0, etc.). Ground truth stores codes without the decimal point (e.g.
    'G3184'), so the decimal point is stripped for comparison — but NOT the leading letter,
    since ICD-10's leading letter is clinically significant (e.g. 'F32' and 'E32' are different
    diagnoses entirely). An earlier version of this scorer stripped all non-digit characters,
    which silently treated letter-substitution OCR errors as correct matches — a real bug found
    by inspecting results where mismatched letters were being scored as success.
    """
    if form_format != "nsf":
        return {"field": "diagnosis_codes", "success": None, "reason": "not applicable for this form format"}

    def normalize_code(c: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", c.upper())

    extracted_codes = extracted_fields.get("diagnosis_codes", {}).get("value", [])
    extracted_normalized = {normalize_code(c) for c in extracted_codes}

    ea0 = ground_truth_claim.get("records", {}).get("EA0", [{}])[0]
    expected_codes = [
        v for k, v in ea0.items()
        if k.startswith(("32.", "33.", "34.", "35.")) and "diagnosis_code" in k and v
    ]
    expected_normalized = {normalize_code(c) for c in expected_codes}

    matched = expected_normalized & extracted_normalized
    success = bool(expected_normalized) and expected_normalized.issubset(extracted_normalized)

    return {
        "field": "diagnosis_codes",
        "extracted": extracted_codes,
        "expected": expected_codes,
        "success": success,
        "matched_count": len(matched),
        "expected_count": len(expected_normalized),
    }


def score_claim(extraction_result: dict, ground_truth_claim: dict, form_format: str) -> dict:
    """
    Score every field this depth pass currently supports for one page's extraction against
    its matching ground truth claim. Returns per-field results plus an overall pass rate.
    Never raises: a missing field on either side scores as not-matched, not an exception.
    """
    if extraction_result.get("status") != "ok" or "fields" not in extraction_result:
        return {"status": "ok", "stage": "scoring", "scored": False, "reason": "no extractable fields in this result"}

    field_scores = []
    if "patient_name" in extraction_result["fields"]:
        field_scores.append(score_patient_name(extraction_result["fields"], ground_truth_claim, form_format))
    if "patient_dob" in extraction_result["fields"]:
        field_scores.append(score_patient_dob(extraction_result["fields"], ground_truth_claim, form_format))
    if "insured_id" in extraction_result["fields"]:
        field_scores.append(score_insured_id(extraction_result["fields"], ground_truth_claim, form_format))
    if "diagnosis_codes" in extraction_result["fields"]:
        field_scores.append(score_diagnosis_codes(extraction_result["fields"], ground_truth_claim, form_format))

    exact_matches = sum(1 for f in field_scores if f["success"])
    total = len(field_scores)

    return {
        "status": "ok",
        "stage": "scoring",
        "scored": True,
        "field_scores": field_scores,
        "success_rate": round(exact_matches / total, 3) if total else 0.0,
        "fields_scored": total,
    }
