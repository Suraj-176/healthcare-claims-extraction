"""
Acceptance test for the Skeleton Pass: the full pipeline must run end-to-end without crashing
on at least one real sample page from every group, and Group D pages must be rejected rather
than force-extracted.

Note: these tests call Tesseract OCR and are slower (~5-20s per page) than the ground truth
parser tests. Run with: pytest tests/test_pipeline_skeleton.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cost.cost_tracker import CostTracker
from pipeline import process_page

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def test_group_a_page_processes_successfully():
    result = process_page(str(DATA_DIR / "Group A" / "M047FJFL.001"), CostTracker())
    assert result["final_status"] == "ok"
    assert result["classification"]["tier"] == "tier_a"


def test_group_c_page_processes_successfully():
    result = process_page(str(DATA_DIR / "Group C" / "M047IJBF.001"), CostTracker())
    assert result["final_status"] == "ok"
    assert result["classification"]["tier"] == "tier_c"


def test_group_d_page_is_rejected_not_crashed():
    """This is the critical Tier D behavior: detect no-content, never fabricate or crash."""
    result = process_page(str(DATA_DIR / "Group D" / "M047KJET.001"), CostTracker())
    assert result["final_status"] == "skipped_reject_no_content"


def test_all_group_c_pages_classify_as_tier_c():
    """
    Regression lock: pages 3 and 5 originally failed to classify (OCR noise meant 'UB-04'
    itself didn't survive) until the keyword list was broadened to include labels that
    survive noisy scans better (STATEMENT COVERS PERIOD, OCCURRENCE SPAN, CONDITION CODES).
    This test ensures that fix doesn't silently regress.
    """
    group_c_dir = DATA_DIR / "Group C"
    image_files = sorted(f for f in group_c_dir.iterdir() if f.suffix.startswith(".0"))
    assert len(image_files) == 6
    for f in image_files:
        result = process_page(str(f), CostTracker())
        assert result["classification"]["tier"] == "tier_c", f"{f.name} misclassified as {result['classification']['tier']}"


def test_nonexistent_file_never_crashes():
    """A missing/corrupt file must return a failed-status dict, never raise."""
    result = process_page(str(DATA_DIR / "Group A" / "does_not_exist.001"), CostTracker())
    # Input validation now catches missing files before preprocessing
    assert result["final_status"] in ("failed_at_validation", "failed_at_preprocessing")
    assert "error" in result["final_status"] or "validation_error" in result
