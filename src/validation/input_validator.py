"""
Production-grade input validation module.

Validates all inputs before processing to prevent crashes and data corruption.
"""

import logging
from pathlib import Path
from typing import Literal
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

ValidationType = Literal["file_exists", "file_type", "image_valid", "image_readable", "image_size"]


def validate_input_file(file_path: str) -> dict:
    """
    Comprehensive input validation with actionable error messages.
    
    Returns:
        {
            "valid": bool,
            "reason": str (if not valid),
            "warnings": list[str],
            "file_info": dict (if valid)
        }
    """
    path = Path(file_path)
    warnings = []
    
    # Check file exists
    if not path.exists():
        return {
            "valid": False,
            "reason": f"File not found: {file_path}",
            "remediation": "Verify the file path is correct and the file exists",
            "warnings": []
        }
    
    # Check file size
    file_size = path.stat().st_size
    if file_size == 0:
        return {
            "valid": False,
            "reason": "File is empty (0 bytes)",
            "remediation": "Provide a valid image file with content",
            "warnings": []
        }
    
    if file_size > 50 * 1024 * 1024:  # 50 MB
        warnings.append(f"Large file ({file_size / 1024 / 1024:.1f} MB) - processing may be slow")
    
    # Check file extension (allow any extension but warn about uncommon ones)
    valid_extensions = {'.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif'}
    common_numeric_extensions = {f'.{str(i).zfill(3)}' for i in range(1, 100)}  # .001 - .099
    
    if path.suffix.lower() not in valid_extensions and path.suffix not in common_numeric_extensions:
        warnings.append(f"Uncommon file extension: {path.suffix} - will attempt to open as image")
    
    # Try to open and validate image
    try:
        with Image.open(path) as img:
            width, height = img.size
            mode = img.mode
            
            # Check if image is readable
            if width == 0 or height == 0:
                return {
                    "valid": False,
                    "reason": "Image has zero dimensions",
                    "remediation": "Provide a valid image file",
                    "warnings": warnings
                }
            
            # Warn about unusual aspect ratios
            aspect_ratio = width / height
            if aspect_ratio > 3 or aspect_ratio < 0.3:
                warnings.append(f"Unusual aspect ratio ({aspect_ratio:.2f}) - may not be a standard claim form")
            
            # Warn about small images
            if width < 800 or height < 800:
                warnings.append(f"Small image ({width}x{height}) - OCR accuracy may be reduced")
            
            # Warn about very large images
            if width > 5000 or height > 5000:
                warnings.append(f"Large image ({width}x{height}) - consider downsampling for faster processing")
            
            # Check if image is grayscale or color
            if mode not in ('RGB', 'L', 'RGBA'):
                warnings.append(f"Unusual color mode ({mode}) - may affect OCR accuracy")
            
            # Try to load pixel data to detect corruption
            try:
                np.array(img)
            except Exception as e:
                return {
                    "valid": False,
                    "reason": f"Image data is corrupted: {str(e)}",
                    "remediation": "Re-scan or re-export the image file",
                    "warnings": warnings
                }
    
    except Exception as e:
        return {
            "valid": False,
            "reason": f"Cannot open image: {str(e)}",
            "remediation": "Verify the file is a valid image (not corrupted or partial download)",
            "warnings": warnings
        }
    
    return {
        "valid": True,
        "warnings": warnings,
        "file_info": {
            "path": str(path),
            "size_bytes": file_size,
            "size_mb": round(file_size / 1024 / 1024, 2),
            "dimensions": (width, height),
            "mode": mode,
            "format": path.suffix.lower()
        }
    }


def validate_extraction_result(result: dict, min_confidence: float = 50.0) -> dict:
    """
    Validate extraction result quality.
    
    Args:
        result: Extraction result from template_ocr or llm_escalation
        min_confidence: Minimum acceptable confidence (0-100)
    
    Returns:
        {
            "quality_passed": bool,
            "quality_score": float,
            "low_confidence_fields": list[str],
            "warnings": list[str]
        }
    """
    if result.get("status") != "ok":
        return {
            "quality_passed": False,
            "quality_score": 0.0,
            "low_confidence_fields": [],
            "warnings": [f"Extraction failed: {result.get('reason', 'Unknown error')}"]
        }
    
    fields = result.get("fields", {})
    if not fields:
        return {
            "quality_passed": False,
            "quality_score": 0.0,
            "low_confidence_fields": [],
            "warnings": ["No fields extracted"]
        }
    
    # Calculate overall confidence
    confidences = []
    low_confidence_fields = []
    
    for field_name, field_data in fields.items():
        if isinstance(field_data, dict) and "confidence" in field_data:
            conf = field_data["confidence"]
            confidences.append(conf)
            if conf < min_confidence:
                low_confidence_fields.append(f"{field_name} ({conf:.1f}%)")
    
    if not confidences:
        avg_confidence = 0.0
    else:
        avg_confidence = sum(confidences) / len(confidences)
    
    quality_score = avg_confidence
    quality_passed = quality_score >= min_confidence and len(low_confidence_fields) == 0
    
    warnings = []
    if low_confidence_fields:
        warnings.append(f"Low confidence fields: {', '.join(low_confidence_fields)}")
    if quality_score < 70:
        warnings.append(f"Overall quality score low ({quality_score:.1f}%) - results may be inaccurate")
    
    return {
        "quality_passed": quality_passed,
        "quality_score": round(quality_score, 1),
        "low_confidence_fields": low_confidence_fields,
        "warnings": warnings
    }
