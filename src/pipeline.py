"""
pipeline.py

End-to-end orchestrator: preprocess -> classify -> extract -> (escalate if needed) ->
validate -> track cost. This is the Skeleton Pass wiring — every stage is present and real,
though extraction/escalation are deliberately crude (whole-page OCR, not yet region-mapped).

Usage:
    python src/pipeline.py --input "data/raw/Group A/M047FJFL.001"
    python src/pipeline.py --input-dir "data/raw/Group A" --output results_group_a.json

Never crashes: every stage is wrapped so a single page's failure is recorded in its result and
does not stop the batch. This is a hard project rule (see spec Section 7).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from classification.page_classifier import classify_page
from cost.cost_tracker import CostTracker
from extraction.llm_escalation import escalate_low_confidence_fields
from extraction.template_ocr import extract_fields_by_anchor, extract_page, FIELD_ANCHORS_BY_FORM
from preprocessing.image_prep import preprocess_page
from validation.business_rules import validate_extraction
from validation.input_validator import validate_input_file, validate_extraction_result

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pipeline")


def check_dependencies() -> dict:
    """
    Check required system dependencies. Returns status dict.
    Never crashes: missing dependencies are reported, not raised.
    """
    issues = []
    
    # Check Tesseract OCR
    tesseract_cmd = os.environ.get("TESSERACT_CMD", "tesseract")
    try:
        result = subprocess.run(
            [tesseract_cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info("Tesseract OCR found: %s", result.stdout.split('\n')[0])
        else:
            issues.append("Tesseract OCR found but returned error")
    except FileNotFoundError:
        issues.append("Tesseract OCR not installed (required for pipeline)")
    except subprocess.TimeoutExpired:
        issues.append("Tesseract OCR check timed out")
    except Exception as exc:
        issues.append(f"Tesseract OCR check failed: {exc}")
    
    # Check Python packages
    try:
        import pytesseract
        import cv2
        import numpy
        from PIL import Image
    except ImportError as exc:
        issues.append(f"Missing Python package: {exc}")
    
    if issues:
        return {
            "status": "failed",
            "issues": issues,
            "recommendation": "See README.md for installation instructions"
        }
    
    return {"status": "ok", "issues": []}


def process_page(path: str, cost_tracker: CostTracker | None = None, min_confidence: float = 50.0) -> dict:
    """
    Run one page through the full pipeline. Always returns a result dict — never raises.
    
    Args:
        path: Path to image file
        cost_tracker: Optional cost tracking
        min_confidence: Minimum acceptable extraction confidence (0-100)
    """
    result = {"input_path": path}
    
    # LOOPHOLE FIX #2: Input validation
    validation = validate_input_file(path)
    if not validation["valid"]:
        result["final_status"] = "failed_at_validation"
        result["validation_error"] = {
            "reason": validation["reason"],
            "remediation": validation.get("remediation", "Fix input file")
        }
        if cost_tracker:
            cost_tracker.record_page("discarded_or_rejected")
        return result
    
    if validation["warnings"]:
        result["input_warnings"] = validation["warnings"]

    prep = preprocess_page(path)
    result["preprocessing"] = {k: v for k, v in prep.items() if k != "image"}
    if prep["status"] != "ok":
        result["final_status"] = "failed_at_preprocessing"
        if cost_tracker:
            cost_tracker.record_page("discarded_or_rejected")
        return result

    classification = classify_page(prep["image"])
    result["classification"] = classification
    tier = classification.get("tier", "unknown_layout")

    if tier in ("reject_no_content", "discard_attachment"):
        result["final_status"] = "skipped_" + tier
        if cost_tracker:
            cost_tracker.record_page("discarded_or_rejected")
        return result

    form_type = classification.get("form_type", "unknown")
    if form_type in FIELD_ANCHORS_BY_FORM:
        extraction = extract_fields_by_anchor(prep["image"], form_type=form_type)
    else:
        extraction = extract_page(prep["image"], form_type=form_type)
    result["extraction"] = extraction
    if extraction["status"] != "ok":
        result["final_status"] = "failed_at_extraction"
        if cost_tracker:
            cost_tracker.record_page("discarded_or_rejected")
        return result

    path_taken = "template_only"
    low_conf = extraction.get("low_confidence_words", [])
    if low_conf:
        escalation = escalate_low_confidence_fields(prep["image"], low_conf)
        result["llm_escalation"] = escalation
        if escalation.get("escalated"):
            path_taken = "llm_escalated"

    validation = validate_extraction(extraction)
    result["validation"] = validation
    
    # LOOPHOLE FIX #4: Quality validation with confidence thresholds
    quality_check = validate_extraction_result(extraction, min_confidence=min_confidence)
    result["quality"] = quality_check

    result["final_status"] = "ok"
    if cost_tracker:
        cost_tracker.record_page(path_taken)
    return result


def process_directory(input_dir: str) -> dict:
    """Process every page file in a directory (non-recursive), skipping non-image files."""
    cost_tracker = CostTracker()
    results = []
    input_path = Path(input_dir)

    if not input_path.is_dir():
        return {"status": "failed", "reason": f"{input_dir} is not a directory"}

    for file_path in sorted(input_path.iterdir()):
        if file_path.is_dir() or file_path.suffix.lower() == ".txt":
            continue
        try:
            page_result = process_page(str(file_path), cost_tracker)
        except Exception as exc:  # absolute last-resort guard — must never propagate
            logger.error("Unhandled error processing %s: %s", file_path, exc)
            page_result = {"input_path": str(file_path), "final_status": "unhandled_error", "reason": str(exc)}
        results.append(page_result)
        logger.info("%s -> %s", file_path.name, page_result.get("final_status"))

    return {
        "status": "ok",
        "pages_processed": len(results),
        "results": results,
        "cost_summary": cost_tracker.summary(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Claims extraction pipeline (Skeleton Pass)")
    parser.add_argument("--input", help="Path to a single page image")
    parser.add_argument("--input-dir", help="Path to a directory of page images")
    parser.add_argument("--output", help="Path to write JSON results (default: stdout)")
    parser.add_argument("--skip-deps-check", action="store_true", help="Skip dependency checking (for testing)")
    args = parser.parse_args()

    if not args.input and not args.input_dir:
        parser.error("Provide either --input or --input-dir")
    
    # Check dependencies unless explicitly skipped
    if not args.skip_deps_check:
        deps_check = check_dependencies()
        if deps_check["status"] == "failed":
            logger.error("Dependency check failed:")
            for issue in deps_check["issues"]:
                logger.error("  - %s", issue)
            logger.error(deps_check["recommendation"])
            sys.exit(1)

    if args.input:
        output = process_page(args.input, CostTracker())
    else:
        output = process_directory(args.input_dir)

    output_json = json.dumps(output, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        logger.info("Results written to %s", args.output)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
