"""
business_rules.py

Enhanced validation with cross-field consistency checks including charge sum validation.
Never crashes: a missing or malformed extraction result is reported as a failed validation,
not an exception.
"""

from __future__ import annotations
import re


def _parse_currency(value: str) -> float:
    """Extract numeric value from currency string. Returns 0.0 on failure."""
    if not value:
        return 0.0
    try:
        cleaned = re.sub(r'[^\d.]', '', str(value))
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def validate_extraction(extraction_result: dict) -> dict:
    """
    Run comprehensive validation checks on one page's extraction result. Handles both 
    extraction shapes: whole-page OCR ('raw_text') and anchor-based field extraction ('fields').
    Includes cross-field consistency checks like charge sum validation. Never raises.
    """
    if extraction_result.get("status") != "ok":
        return {"status": "ok", "stage": "validation", "valid": False,
                "reason": "upstream extraction did not succeed"}

    issues = []
    warnings = []

    if "fields" in extraction_result:
        fields = extraction_result["fields"]
        found_any = any(f.get("value") for f in fields.values())
        if not found_any:
            issues.append("no fields could be extracted from page")
        
        missing = [name for name, f in fields.items() if not f.get("found_anchor")]
        if missing:
            warnings.append(f"anchor not found for fields: {', '.join(missing)}")
        
        # Charge sum validation for CMS-1500
        if "service_lines" in fields and "total_charge" in fields:
            service_lines = fields["service_lines"].get("value", [])
            total_charge_str = fields["total_charge"].get("value", "")
            
            if service_lines and total_charge_str:
                line_sum = sum(_parse_currency(line.get("charges", "0")) for line in service_lines)
                stated_total = _parse_currency(total_charge_str)
                
                if line_sum > 0 and stated_total > 0:
                    diff = abs(line_sum - stated_total)
                    tolerance = max(stated_total * 0.01, 0.50)  # 1% or 50 cents
                    if diff > tolerance:
                        issues.append(
                            f"charge sum mismatch: service lines sum to ${line_sum:.2f} "
                            f"but total charge is ${stated_total:.2f} (diff: ${diff:.2f})"
                        )
        
        # Charge sum validation for UB-04
        if "revenue_lines" in fields and "total_charges" in fields:
            revenue_lines = fields["revenue_lines"].get("value", [])
            total_charges_str = fields["total_charges"].get("value", "")
            
            if revenue_lines and total_charges_str:
                line_sum = sum(_parse_currency(line.get("charges", "0")) for line in revenue_lines)
                stated_total = _parse_currency(total_charges_str)
                
                if line_sum > 0 and stated_total > 0:
                    diff = abs(line_sum - stated_total)
                    tolerance = max(stated_total * 0.01, 0.50)
                    if diff > tolerance:
                        issues.append(
                            f"charge sum mismatch: revenue lines sum to ${line_sum:.2f} "
                            f"but total charges is ${stated_total:.2f} (diff: ${diff:.2f})"
                        )
        
        # Date consistency checks
        if "patient_dob" in fields:
            dob_str = fields["patient_dob"].get("value", "")
            if dob_str:
                # Check if DOB is in the future
                import datetime
                try:
                    # Try to parse common date formats
                    for fmt in ["%m-%d-%Y", "%m/%d/%Y", "%Y%m%d"]:
                        try:
                            dob = datetime.datetime.strptime(dob_str.replace(" ", ""), fmt)
                            if dob > datetime.datetime.now():
                                warnings.append(f"patient DOB appears to be in the future: {dob_str}")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass  # Skip date validation if parsing fails
    else:
        raw_text = extraction_result.get("raw_text", "")
        if not raw_text.strip():
            issues.append("no text extracted from page")

    mean_conf = extraction_result.get("mean_confidence", 0.0)
    if mean_conf < 40.0:
        warnings.append(f"very low mean OCR confidence ({mean_conf})")

    return {
        "status": "ok",
        "stage": "validation",
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }
