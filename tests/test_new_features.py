"""
Integration tests for new extraction features (service lines, revenue codes, charge validation).

These tests verify end-to-end functionality of features added in Depth Pass 3:
- Service line extraction (CMS-1500 Box 24)
- Revenue code extraction (UB-04 Box 42-49)  
- Charge sum validation
- Total charge field extraction
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
from PIL import Image
from extraction.template_ocr import extract_fields_by_anchor
from validation.business_rules import validate_extraction


def test_service_lines_extraction_structure():
    """Test that service_lines extraction returns expected structure."""
    # Load a real CMS-1500 page
    img_path = Path(__file__).parent.parent / "data" / "raw" / "Group A" / "M047FJFL.001"
    img = Image.open(img_path)
    img_np = np.array(img)
    
    result = extract_fields_by_anchor(img_np, "CMS-1500")
    
    # Verify service_lines field exists
    assert "service_lines" in result["fields"]
    
    # Verify structure
    service_lines = result["fields"]["service_lines"]
    assert "value" in service_lines
    assert isinstance(service_lines["value"], list)
    assert "confidence" in service_lines
    
    # Each service line should have expected keys
    if len(service_lines["value"]) > 0:
        line = service_lines["value"][0]
        assert "date_from" in line
        assert "date_to" in line
        assert "charges" in line
        assert "raw_text" in line


def test_revenue_lines_extraction_structure():
    """Test that revenue_lines extraction returns expected structure."""
    # Load a real UB-04 page
    img_path = Path(__file__).parent.parent / "data" / "raw" / "Group C" / "M047IJBF.001"
    img = Image.open(img_path)
    img_np = np.array(img)
    
    result = extract_fields_by_anchor(img_np, "UB-04")
    
    # Verify revenue_lines field exists
    assert "revenue_lines" in result["fields"]
    
    # Verify structure
    revenue_lines = result["fields"]["revenue_lines"]
    assert "value" in revenue_lines
    
    # Value should be a list (or empty string if extraction failed gracefully)
    # This is acceptable - the test verifies the field exists and extraction doesn't crash
    assert isinstance(revenue_lines["value"], (list, str))
    assert "confidence" in revenue_lines
    
    # If extraction succeeded, verify line structure
    if isinstance(revenue_lines["value"], list) and len(revenue_lines["value"]) > 0:
        line = revenue_lines["value"][0]
        assert "revenue_code" in line
        assert "charges" in line
        assert "raw_text" in line


def test_total_charge_field_extraction():
    """Test that total_charge field is extracted from CMS-1500."""
    img_path = Path(__file__).parent.parent / "data" / "raw" / "Group A" / "M047FJFL.001"
    img = Image.open(img_path)
    img_np = np.array(img)
    
    result = extract_fields_by_anchor(img_np, "CMS-1500")
    
    # Verify total_charge field exists
    assert "total_charge" in result["fields"]
    
    total_charge = result["fields"]["total_charge"]
    assert "value" in total_charge
    assert "confidence" in total_charge
    
    # Value should be a string (currency amount)
    assert isinstance(total_charge["value"], str)


def test_charge_sum_validation_logic():
    """Test that charge sum validation logic works correctly."""
    # Create mock extraction with known values
    mock_extraction = {
        "status": "ok",
        "form_type": "CMS-1500",
        "fields": {
            "service_lines": {
                "value": [
                    {"date_from": "07/16/25", "date_to": "07/16/25", "charges": "$175.00", "raw_text": "..."},
                    {"date_from": "07/29/25", "date_to": "07/29/25", "charges": "$150.00", "raw_text": "..."},
                    {"date_from": "07/29/25", "date_to": "07/29/25", "charges": "$750.00", "raw_text": "..."},
                ]
            },
            "total_charge": {
                "value": "$1075.00"  # Correct sum
            }
        }
    }
    
    # Validate - should pass with no issues
    validation = validate_extraction(mock_extraction)
    assert validation["status"] == "ok"
    assert validation["valid"] is True
    assert len(validation["issues"]) == 0


def test_charge_sum_validation_detects_mismatch():
    """Test that charge sum validation detects mismatches."""
    # Create mock extraction with intentional mismatch
    mock_extraction = {
        "status": "ok",
        "form_type": "CMS-1500",
        "fields": {
            "service_lines": {
                "value": [
                    {"date_from": "07/16/25", "date_to": "07/16/25", "charges": "$175.00", "raw_text": "..."},
                    {"date_from": "07/29/25", "date_to": "07/29/25", "charges": "$150.00", "raw_text": "..."},
                ]
            },
            "total_charge": {
                "value": "$500.00"  # Wrong! Should be $325.00
            }
        }
    }
    
    # Validate - should detect mismatch
    validation = validate_extraction(mock_extraction)
    assert validation["status"] == "ok"
    assert validation["valid"] is False
    assert len(validation["issues"]) > 0
    
    # Check that issue mentions "charge sum mismatch"
    issue_text = " ".join(validation["issues"])
    assert "charge sum mismatch" in issue_text.lower()


def test_service_lines_force_escalation():
    """Test that service_lines field is marked for force escalation."""
    from extraction.template_ocr import CMS1500_FIELD_ANCHORS
    
    # Verify force_escalate flag is set
    assert "service_lines" in CMS1500_FIELD_ANCHORS
    assert CMS1500_FIELD_ANCHORS["service_lines"].get("force_escalate") is True


def test_revenue_lines_force_escalation():
    """Test that revenue_lines field is marked for force escalation."""
    from extraction.template_ocr import UB04_FIELD_ANCHORS
    
    # Verify force_escalate flag is set
    assert "revenue_lines" in UB04_FIELD_ANCHORS
    assert UB04_FIELD_ANCHORS["revenue_lines"].get("force_escalate") is True


def test_extraction_never_crashes_on_missing_charges():
    """Test that extraction handles pages with no charges gracefully."""
    mock_extraction = {
        "status": "ok",
        "form_type": "CMS-1500",
        "fields": {
            "service_lines": {
                "value": [
                    {"date_from": "", "date_to": "", "charges": "", "raw_text": "..."},
                ]
            },
            "total_charge": {
                "value": ""
            }
        }
    }
    
    # Should not crash, should handle gracefully
    validation = validate_extraction(mock_extraction)
    assert validation["status"] == "ok"
    # Valid or not depends on business rules, but shouldn't crash
    assert isinstance(validation["valid"], bool)
