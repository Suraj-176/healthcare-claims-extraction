"""
Depth Pass 3 accuracy regression test.

This locks in the real, measured patient-name extraction accuracy against ground truth for
all 12 real Group A claims. The number here (8/12 = 66.7%) was arrived at by actually running
the pipeline and fixing two real bugs found in the process (an off-by-a-few-pixels boundary
issue, and a right-hand bound bleeding into the adjacent form field) — it is not a target we
wrote code to hit, it's what the code actually does. This test exists so future changes to the
extraction or scoring logic can't silently regress this number without being caught.

Known remaining failures (006, 007, 009, 011) are due to genuinely poor OCR legibility on
those specific scans (the box-2 label itself doesn't survive OCR, or the value text is
garbled) — see project spec for the plan to address these with a positional-prior fallback.
"""

import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from extraction.template_ocr import extract_fields_by_anchor
from ground_truth.ground_truth_parser import build_spec_maps, parse_ground_truth_file
from preprocessing.image_prep import load_page
from scoring.accuracy_scorer import score_claim

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MINIMUM_ACCEPTABLE_SUCCESS_RATE = 0.60  # real measured rate is 8/12 = 0.667; alert if it drops


def test_group_a_patient_name_accuracy_meets_minimum_bar():
    nsf_spec, _ = build_spec_maps(
        DATA_DIR / "specs" / "NSF_Matrix.txt", DATA_DIR / "specs" / "UB92_File_Specs.txt"
    )
    gt_path = DATA_DIR / "raw" / "Group A" / "DATAMATICS_UBH_HCFA_07212026 - Group A.txt"
    claims = parse_ground_truth_file(gt_path, nsf_spec=nsf_spec, file_format="nsf")

    image_files = sorted(
        f for f in glob.glob(str(DATA_DIR / "raw" / "Group A" / "M047FJFL.0*"))
        if not f.endswith(".txt")
    )
    assert len(image_files) == len(claims) == 12

    successes = 0
    for i, f in enumerate(image_files):
        img = load_page(f)
        extraction = extract_fields_by_anchor(img, "CMS-1500")
        score = score_claim(extraction, claims[i], "nsf")
        name_score = next((s for s in score["field_scores"] if s["field"] == "patient_name"), None)
        if name_score and name_score["success"]:
            successes += 1

    success_rate = successes / len(image_files)
    assert success_rate >= MINIMUM_ACCEPTABLE_SUCCESS_RATE, (
        f"Patient-name extraction accuracy dropped to {success_rate:.1%} "
        f"(minimum acceptable: {MINIMUM_ACCEPTABLE_SUCCESS_RATE:.0%}) — check recent changes "
        f"to extraction/template_ocr.py or scoring/accuracy_scorer.py"
    )


def test_patient_dob_is_always_force_escalated():
    """
    Real testing showed anchor-based DOB extraction is only ~25% accurate (vs ~67% for
    patient_name) due to higher layout variance in narrow date-digit boxes. Rather than keep
    tuning pixel offsets with diminishing returns, DOB is deliberately always routed to LLM
    escalation regardless of measured OCR confidence. This test locks that routing decision in
    so it can't be silently lost in a future refactor.
    """
    from extraction.template_ocr import extract_fields_by_anchor

    img = load_page(str(DATA_DIR / "raw" / "Group A" / "M047FJFL.001"))
    result = extract_fields_by_anchor(img, "CMS-1500")
    escalated_fields = {f["word"] for f in result["low_confidence_words"]}
    assert "patient_dob" in escalated_fields, (
        "patient_dob must always be force-escalated to LLM review — see force_escalate flag "
        "in CMS1500_FIELD_ANCHORS"
    )


def test_insured_id_is_always_force_escalated():
    """
    Real testing across all 12 Group A claims showed only 25% (3/12) accuracy for insured_id
    via anchor-based OCR — same pattern as patient_dob. Numeric/ID fields are consistently
    less reliable via this technique than wide text fields, so this field is always escalated.
    """
    from extraction.template_ocr import extract_fields_by_anchor

    img = load_page(str(DATA_DIR / "raw" / "Group A" / "M047FJFL.001"))
    result = extract_fields_by_anchor(img, "CMS-1500")
    escalated_fields = {f["word"] for f in result["low_confidence_words"]}
    assert "insured_id" in escalated_fields, (
        "insured_id must always be force-escalated to LLM review — see force_escalate flag "
        "in CMS1500_FIELD_ANCHORS"
    )


def test_diagnosis_codes_is_always_force_escalated():
    """
    Real testing across all 12 Group A claims showed only 16.7% (2/12) accuracy for
    diagnosis_codes using a letter-sensitive scorer (an earlier, looser digit-only scorer
    misleadingly reported 33.3% by ignoring clinically significant letter-substitution errors
    like 'F' being misread as 'E'). Escalated for the same reason as other structured fields.
    """
    from extraction.template_ocr import extract_fields_by_anchor

    img = load_page(str(DATA_DIR / "raw" / "Group A" / "M047FJFL.001"))
    result = extract_fields_by_anchor(img, "CMS-1500")
    escalated_fields = {f["word"] for f in result["low_confidence_words"]}
    assert "diagnosis_codes" in escalated_fields, (
        "diagnosis_codes must always be force-escalated to LLM review — see force_escalate "
        "flag in CMS1500_FIELD_ANCHORS"
    )


def test_ub04_fields_are_always_force_escalated():
    """
    Real testing across 6 Group C samples showed the UB-04 box-8 label-to-value gap varies
    wildly between scans (same-line on one page, ~260px below on another), so a fixed
    anchor-band sweeps in unrelated content rather than isolating the value. Both UB-04 fields
    are deliberately always escalated rather than trusted from an unreliable OCR-band read.
    This test locks that decision in across every real sample in the group.
    """
    import glob as glob_module
    from extraction.template_ocr import extract_fields_by_anchor

    files = sorted(
        f for f in glob_module.glob(str(DATA_DIR / "raw" / "Group C" / "M047IJBF.0*"))
        if not f.endswith(".txt")
    )
    assert len(files) == 6

    for f in files:
        img = load_page(f)
        result = extract_fields_by_anchor(img, "UB-04")
        escalated_fields = {w["word"] for w in result["low_confidence_words"]}
        assert "patient_name" in escalated_fields, f"{f}: patient_name should always be force-escalated"
        assert "patient_dob" in escalated_fields, f"{f}: patient_dob should always be force-escalated"
