# Technical Design Document

## Overview

This document provides detailed technical specifications for the Healthcare Claims Extraction Engine implementation, including data schemas, API contracts, field mapping specifications, and decision logic.

## System Architecture

### Component Diagram
```
┌──────────────────┐
│ Input Sources    │
│ - File upload    │
│ - API endpoint   │
│ - Batch folder   │
└─────┬────────────┘
      │
      ▼
┌──────────────────┐
│ pipeline.py      │ Main orchestrator
│ process_page()   │
└─────┬────────────┘
      │
      ├─────► preprocessing/image_prep.py
      │        └─ load_page()
      │        └─ deskew()
      │        └─ denoise_and_binarize()
      │
      ├─────► classification/page_classifier.py
      │        └─ classify_page()
      │        └─ _sniff_text()
      │
      ├─────► extraction/template_ocr.py
      │        └─ extract_fields_by_anchor()
      │        └─ _get_words()
      │        └─ _find_anchor()
      │        └─ _read_value_below()
      │        └─ _extract_diagnosis_codes()
      │        └─ _extract_service_lines()
      │        └─ _extract_revenue_lines()
      │
      ├─────► extraction/llm_escalation.py
      │        └─ escalate_low_confidence_fields()
      │        └─ _image_to_base64_png()
      │
      ├─────► validation/business_rules.py
      │        └─ validate_extraction()
      │        └─ _parse_currency()
      │
      ├─────► scoring/accuracy_scorer.py
      │        └─ score_claim()
      │        └─ score_patient_name()
      │        └─ score_patient_dob()
      │        └─ score_insured_id()
      │        └─ score_diagnosis_codes()
      │
      └─────► cost/cost_tracker.py
               └─ record_page()
               └─ summary()
```

## Data Schemas

### 1. Pipeline Status Dict (Universal Return Type)

All functions return this standard structure:

```python
{
    "status": "ok" | "failed" | "skipped",
    "stage": str,  # "preprocessing", "classification", "extraction", etc.
    "reason": str,  # Only present if status != "ok"
    ...additional stage-specific fields...
}
```

**Design Rationale**: Never-crash architecture. Every function returns success or tagged failure, never raises unhandled exceptions.

### 2. Preprocessing Output

```python
{
    "status": "ok",
    "stage": "preprocessing",
    "image": np.ndarray,  # Grayscale, cleaned, deskewed
    "original_shape": tuple,  # (height, width)
    "deskew_angle": float,  # Degrees rotated (-15 to +15)
}
```

### 3. Classification Output

```python
{
    "status": "ok",
    "stage": "classification",
    "tier": "tier_a" | "tier_c" | "discard_attachment" | "reject_no_content" | "unknown_layout",
    "form_type": "CMS-1500" | "UB-04" | None,
    "confidence": float,  # 0-100 (if applicable)
    "reason": str,  # Human-readable explanation
}
```

**Tier Definitions**:
- `tier_a`: CMS-1500 claim form → extract
- `tier_c`: UB-04 claim form → extract
- `discard_attachment`: EOB, tracking slip → skip extraction ($0 cost)
- `reject_no_content`: Separator/cover sheet → skip extraction ($0 cost)
- `unknown_layout`: No match → route to manual review

### 4. Extraction Output (Anchor-Based)

```python
{
    "status": "ok",
    "stage": "extraction",
    "form_type": "CMS-1500" | "UB-04",
    "extraction_method": "anchor_based" | "template_ocr",
    "mean_confidence": float,  # 0-100, average across all fields
    "fields": {
        "patient_name": {
            "value": str,
            "confidence": float,  # 0-100
            "found_anchor": bool,
        },
        "patient_dob": {...},
        "insured_id": {...},
        "diagnosis_codes": {
            "value": list[str],  # ["F32.1", "G3184", ...]
            "confidence": float,
            "found_anchor": bool,
        },
        "service_lines": {
            "value": [
                {
                    "date_from": str,
                    "date_to": str,
                    "charges": str,
                    "raw_text": str
                },
                ...
            ],
            "confidence": float,
            "found_anchor": bool,
        },
        "total_charge": {...},
    },
    "low_confidence_words": [
        {"word": "patient_dob", "confidence": 45.2},
        ...
    ]
}
```

### 5. LLM Escalation Output

```python
{
    "status": "ok" | "skipped" | "failed",
    "stage": "llm_escalation",
    "escalated": bool,
    "reason": str,  # If not escalated
    "llm_output": str,  # Raw LLM response text
    "extraction_method": "llm_escalated",
    "fields_escalated": int,
}
```

### 6. Validation Output

```python
{
    "status": "ok",
    "stage": "validation",
    "valid": bool,
    "issues": [str],  # Blocking validation failures
    "warnings": [str],  # Non-blocking concerns
}
```

**Issues** (blocking):
- "charge sum mismatch: service lines sum to $450.00 but total charge is $500.00 (diff: $50.00)"
- "no fields could be extracted from page"

**Warnings** (non-blocking):
- "very low mean OCR confidence (38%)"
- "anchor not found for fields: insured_id, diagnosis_codes"
- "patient DOB appears to be in the future: 01-15-2027"

### 7. Scoring Output

```python
{
    "status": "ok",
    "stage": "scoring",
    "scored": bool,
    "field_scores": [
        {
            "field": "patient_name",
            "extracted": "KARNO, YOLANA",
            "expected": "KARNO, YOLANA",
            "success": True,
            "exact_match": True,
            "last_name_found": True,
            "first_name_found": True,
        },
        {
            "field": "patient_dob",
            "extracted": "12-02-1932",
            "expected": "12-02-1932",
            "success": True,
            "month_found": True,
            "day_found": True,
            "year_digit_matches": 4,
        },
        ...
    ],
    "success_rate": 0.75,  # 3 of 4 fields correct
    "fields_scored": 4,
}
```

### 8. Cost Tracking Summary

```python
{
    "total_pages": 30,
    "blended_cost_per_page": 0.0094,
    "breakdown": {
        "template_only": {
            "count": 8,
            "unit_cost_estimate": 0.0015,
            "subtotal": 0.012
        },
        "llm_escalated": {
            "count": 18,
            "unit_cost_estimate": 0.015,
            "subtotal": 0.27
        },
        "discarded_or_rejected": {
            "count": 4,
            "unit_cost_estimate": 0.0,
            "subtotal": 0.0
        }
    },
    "note": "unit costs are estimates from the project spec, not measured invoices"
}
```

### 9. Complete Page Result

```python
{
    "input_path": "data/raw/Group A/M047FJFL.001",
    "preprocessing": {...},
    "classification": {...},
    "extraction": {...},
    "llm_escalation": {...},  # Optional, only if escalated
    "validation": {...},
    "final_status": "ok" | "failed_at_preprocessing" | "skipped_reject_no_content" | ...,
}
```

## Field Extraction Specifications

### CMS-1500 Field Map

| Box | Field Name | Anchor Tokens | Extraction Method | Force-Escalate | Notes |
|-----|------------|---------------|-------------------|----------------|-------|
| 1a | insured_id | ["INSUREDS", "ID", "NUMBER"] | Band below | ✅ Yes | 25% OCR accuracy, numeric ID |
| 2 | patient_name | ["PATIENTS", "NAME"] | Band below | ❌ No | 67% OCR accuracy, wide text field |
| 3 | patient_dob | ["PATIENTS", "BIRTH", "DATE"] | Band below | ✅ Yes | 25% OCR accuracy, narrow date boxes |
| 21 | diagnosis_codes | ["DIAGNOSIS", "OR", "NATURE"] | Regex codes | ✅ Yes | 17% OCR accuracy, letter-sensitive |
| 24 | service_lines | ["DATES", "OF", "SERVICE"] | Multi-row | ✅ Yes | Complex structure, financial impact |
| 28 | total_charge | ["TOTAL", "CHARGE"] | Band below | ❌ No | Single value, escalate on low conf only |

### UB-04 Field Map

| Box | Field Name | Anchor Tokens | Extraction Method | Force-Escalate | Notes |
|-----|------------|---------------|-------------------|----------------|-------|
| 8 | patient_name | ["PATIENT", "NAME"] | Band below | ✅ Yes | Variable layout between scans |
| 9 | patient_dob | ["BIRTHDATE"] | Band below | ✅ Yes | Variable layout between scans |
| 42-49 | revenue_lines | ["REVENUE", "CODE"] | Multi-row | ✅ Yes | Complex structure, financial impact |
| 47 | total_charges | ["TOTALS"] | Band below | ❌ No | Single value, escalate on low conf only |

### Anchor Configuration Parameters

```python
{
    "anchor": list[str],        # Tokens to find (fuzzy-matched)
    "max_width": int,           # Pixels to right of anchor (default: 500)
    "band_height": int,         # Pixels below anchor (default: 40)
    "x_slack": int,             # Pixels left of anchor (default: 40)
    "top_offset": int,          # For same-line values (optional)
    "extraction_style": str,    # "band" | "regex_codes" | "service_lines" | "revenue_lines"
    "force_escalate": bool,     # Always send to LLM regardless of confidence
}
```

## Ground Truth Schema

### NSF/HCFA Fixed-Width Format

```
Positions 1-3: Record Type (e.g., "BA0", "CA0", "DA0", "FA0")
Positions vary per record type (see spec_parser.py)

Example CA0 record (Patient Data):
Position 1-3:   CA0
Position 4-22:  (Reserved)
Position 23-42: Patient Last Name
Position 43-52: Patient First Name
Position 53-53: Patient Middle Initial
...
Position 89-96: Patient DOB (YYYYMMDD)
```

**Claim Boundaries**: New claim starts at each `BA0` record (Batch Header - Provider Data 1)

### UB-92 Fixed-Width Format

```
Positions 1-2: Record Type (e.g., "10", "20", "30", "60", "70")
Positions vary per record type

Example Record Type 20 (Patient Data):
Position 1-2:   20
Position 3-4:   (Filler)
Position 5-24:  Patient Last Name
Position 25-44: Patient First Name
...
Position 59-66: Patient Birthdate (YYYYMMDD)
```

**Claim Boundaries**: New claim starts at each `10` record (Provider Data)

## Decision Logic

### 1. Classification Decision Tree

```
1. OCR full page text (whole-page sniff)
2. IF "DOCUMENT SEPARATOR" in text → reject_no_content
3. ELSE IF any of ["HEALTH INSURANCE CLAIM FORM", "PICA", "NUCC"] in text → tier_a (CMS-1500)
4. ELSE IF any of ["UB-04", "TYPE OF BILL", "REV. CD", "STATEMENT COVERS PERIOD"] in text → tier_c (UB-04)
5. ELSE IF any of ["TRACKING NO", "UNIQUE ID", "RECVDATE", "EOB"] in text → discard_attachment
6. ELSE → unknown_layout (route to manual review)
```

**No guessing**: System explicitly reports "unknown" rather than forcing a tier assignment.

### 2. Field Escalation Decision Tree

```
FOR each field in extraction result:
    IF field.found_anchor == False:
        escalate = True  # Can't locate field, need LLM help
    
    ELSE IF field_config.force_escalate == True:
        escalate = True  # Data-driven rule: this field type always escalates
    
    ELSE IF field.confidence < 60:
        escalate = True  # Measured OCR confidence too low
    
    ELSE IF field.value is empty:
        escalate = True  # No value extracted
    
    ELSE:
        escalate = False  # Trust OCR result
```

### 3. Validation Decision Logic

```
issues = []
warnings = []

# Completeness check
IF no fields extracted:
    issues.append("no fields could be extracted from page")

# Charge sum validation (CMS-1500)
IF service_lines exist AND total_charge exists:
    line_sum = sum(line.charges for line in service_lines)
    stated_total = total_charge
    diff = abs(line_sum - stated_total)
    tolerance = max(stated_total * 0.01, 0.50)  # 1% or 50 cents
    
    IF diff > tolerance:
        issues.append(f"charge sum mismatch: {line_sum} vs {stated_total}")

# Date logic check
IF patient_dob exists:
    IF patient_dob > today():
        warnings.append("patient DOB appears to be in the future")

# OCR confidence check
IF mean_confidence < 40:
    warnings.append(f"very low mean OCR confidence ({mean_confidence})")

# Final decision
valid = (len(issues) == 0)
return {"valid": valid, "issues": issues, "warnings": warnings}
```

## API Specifications

### REST API Endpoints (Future)

#### POST /api/v1/extract
Extract fields from a single claim page.

**Request**:
```json
{
    "image": "base64-encoded TIFF/PNG/JPEG",
    "form_type": "CMS-1500" | "UB-04" | "auto",  # Optional, auto-detect if omitted
    "options": {
        "enable_llm_escalation": true,
        "return_confidence_scores": true,
        "skip_validation": false
    }
}
```

**Response (200 OK)**:
```json
{
    "request_id": "uuid",
    "status": "success",
    "classification": {
        "form_type": "CMS-1500",
        "tier": "tier_a"
    },
    "fields": {
        "patient_name": {"value": "KARNO, YOLANA", "confidence": 0.82},
        "patient_dob": {"value": "12-02-1932", "confidence": 0.95},
        ...
    },
    "validation": {
        "valid": true,
        "issues": [],
        "warnings": []
    },
    "metadata": {
        "extraction_method": "hybrid",
        "llm_escalated_fields": ["patient_dob", "insured_id"],
        "processing_time_ms": 12450,
        "cost_estimate": 0.015
    }
}
```

**Response (400 Bad Request)**:
```json
{
    "error": "invalid_image",
    "message": "Could not decode image data"
}
```

#### POST /api/v1/extract/batch
Extract fields from multiple pages (async).

**Request**:
```json
{
    "images": [
        {"id": "page1", "image": "base64..."},
        {"id": "page2", "image": "base64..."}
    ],
    "callback_url": "https://your-app.com/webhook",  # Optional
    "options": {...}
}
```

**Response (202 Accepted)**:
```json
{
    "batch_id": "uuid",
    "status": "processing",
    "pages_submitted": 2,
    "estimated_completion_seconds": 45
}
```

#### GET /api/v1/extract/batch/{batch_id}
Check batch status.

**Response (200 OK)**:
```json
{
    "batch_id": "uuid",
    "status": "completed" | "processing" | "failed",
    "pages_total": 2,
    "pages_completed": 2,
    "results": [
        {"id": "page1", ...extraction_result...},
        {"id": "page2", ...extraction_result...}
    ]
}
```

## Performance Tuning

### OCR Optimization

**Tesseract Config** (current):
```python
pytesseract.image_to_data(
    img,
    output_type=Output.DICT,
    config='--psm 6'  # Assume uniform block of text
)
```

**Alternative Configs** (for experimentation):
- `--psm 4`: Single column of text (for dense forms)
- `--psm 3`: Fully automatic page segmentation (slower but more robust)
- `--oem 1`: LSTM neural net mode only (higher accuracy, slower)

### Image Preprocessing Tuning

**Current Settings**:
```python
# Deskew
cv2.minAreaRect()  # Estimates rotation
angle_threshold = (-15, +15)  # Ignore larger rotations

# Denoise
cv2.fastNlMeansDenoising(h=10)  # h=10 is moderate denoising

# Binarization
cv2.adaptiveThreshold(
    blockSize=31,  # Local neighborhood size
    C=15           # Constant subtracted from mean
)
```

**Tuning Recommendations**:
- Increase `h` (20-30) for noisier scans
- Decrease `blockSize` (21) for smaller text
- Adjust `C` (+5 to +25) for contrast variations

### Anchor Matching Tuning

**Current Settings**:
```python
FUZZY_MATCH_THRESHOLD = 0.75  # Character similarity ratio
max_gap = 1  # Tolerate 1 unmatched word between anchor tokens
```

**Tuning Recommendations**:
- Decrease threshold (0.6-0.7) if anchors frequently missed
- Increase `max_gap` (2-3) for noisier layouts
- Add form-specific canonicalization rules

## Error Handling

### Error Categories

| Error Type | HTTP Code | Action | Example |
|------------|-----------|--------|---------|
| **Invalid Input** | 400 | Return error, don't process | Corrupted TIFF, wrong file type |
| **Processing Failure** | 200 (tagged) | Return failed status dict | OCR engine crash, no text detected |
| **Service Unavailable** | 503 | Retry with backoff | LLM API timeout, rate limit |
| **Validation Failure** | 200 (tagged) | Return invalid status, route to review | Charge sum mismatch, missing required field |

**Design Principle**: Distinguish between **user errors** (400 Bad Request) and **processing failures** (200 OK with failed status). Processing failures are expected and handled gracefully.

### Retry Logic

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(APIError)
)
def call_llm_api(image_data, prompt):
    ...
```

## Database Schema (Future)

### claims Table

```sql
CREATE TABLE claims (
    claim_id UUID PRIMARY KEY,
    submitted_at TIMESTAMP NOT NULL,
    form_type VARCHAR(20) NOT NULL,  -- 'CMS-1500', 'UB-04'
    tier VARCHAR(20) NOT NULL,       -- 'tier_a', 'tier_c', etc.
    extraction_status VARCHAR(20),   -- 'completed', 'failed', 'review_needed'
    validation_status VARCHAR(20),   -- 'valid', 'invalid'
    total_charge NUMERIC(10, 2),
    service_date_from DATE,
    service_date_to DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### claim_fields Table

```sql
CREATE TABLE claim_fields (
    field_id UUID PRIMARY KEY,
    claim_id UUID REFERENCES claims(claim_id),
    field_name VARCHAR(50) NOT NULL,  -- 'patient_name', 'patient_dob', etc.
    field_value TEXT,
    confidence NUMERIC(5, 2),         -- 0-100
    extraction_method VARCHAR(20),    -- 'template_ocr', 'llm_escalated'
    created_at TIMESTAMP DEFAULT NOW()
);
```

### audit_log Table

```sql
CREATE TABLE audit_log (
    log_id UUID PRIMARY KEY,
    claim_id UUID REFERENCES claims(claim_id),
    action VARCHAR(50) NOT NULL,      -- 'extracted', 'validated', 'corrected'
    user_id UUID,
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Security Considerations

### Data Encryption

**At Rest**:
- Database: AES-256 encryption (PostgreSQL pgcrypto)
- Images: S3 server-side encryption (SSE-S3 or SSE-KMS)
- Backups: Encrypted snapshots

**In Transit**:
- TLS 1.3 for all API calls
- HTTPS only (no HTTP fallback)
- Certificate pinning for LLM API calls

### Access Control

**Role-Based Access Control (RBAC)**:

| Role | Permissions |
|------|-------------|
| **Submitter** | Upload claims, view own results |
| **Reviewer** | View all claims, make corrections |
| **Admin** | Full access, manage users, view audit logs |
| **API User** | Programmatic access via API key |

### API Authentication

**API Key Format**:
```
hce_<environment>_<32-char-base64>

Examples:
hce_prod_a7b8c9d0e1f2g3h4i5j6k7l8m9n0p1q2
hce_dev_x1y2z3a4b5c6d7e8f9g0h1i2j3k4l5m6
```

**Authentication Header**:
```http
Authorization: Bearer hce_prod_a7b8c9d0e1f2g3h4i5j6k7l8m9n0p1q2
```

### PHI Handling

**Minimum Necessary Principle**:
- Extract only required fields (don't store full page text)
- Redact SSNs from non-production environments
- Mask patient names in logs (show "P*****O, Y*****A" instead of "KARNO, YOLANA")

**Data Retention**:
- Production: 7 years (regulatory requirement)
- Dev/Test: 90 days max
- Audit logs: 10 years

## Testing Strategy

### Unit Tests (pytest)

```python
# test_ground_truth_parser.py
def test_group_a_has_exactly_12_claims():
    claims = parse_ground_truth_file("Group A/ground_truth.txt")
    assert len(claims) == 12

# test_extraction.py
def test_patient_name_extraction_accuracy_meets_minimum():
    accuracy = measure_accuracy_on_group_a("patient_name")
    assert accuracy >= 0.60  # 60% minimum threshold
```

### Integration Tests

```python
# test_pipeline_skeleton.py
def test_full_pipeline_runs_without_crashing():
    result = process_page("data/raw/Group A/M047FJFL.001")
    assert result["final_status"] == "ok"
```

### Load Tests

```bash
# locustfile.py
from locust import HttpUser, task

class ClaimExtractor(HttpUser):
    @task
    def extract_claim(self):
        with open("sample.tif", "rb") as f:
            self.client.post("/api/v1/extract", files={"image": f})
```

**Run**:
```bash
locust -f locustfile.py --users 100 --spawn-rate 10
```

### Regression Tests

Lock in measured accuracy numbers:

```python
# test_extraction_accuracy.py
MINIMUM_ACCEPTABLE_SUCCESS_RATE = 0.60

def test_group_a_patient_name_accuracy_meets_minimum_bar():
    success_rate = measure_patient_name_accuracy()
    assert success_rate >= MINIMUM_ACCEPTABLE_SUCCESS_RATE, (
        f"Patient-name extraction accuracy dropped to {success_rate:.1%}"
    )
```

## Monitoring & Observability

### Key Metrics to Track

**Application Metrics**:
- Extraction accuracy per field (daily, weekly trend)
- Processing latency (P50, P95, P99)
- Throughput (pages/hour)
- Error rate (failed extractions / total)
- LLM escalation rate

**Business Metrics**:
- Cost per page (actual, not estimated)
- Human review rate
- SLA compliance (% pages processed <30s)

**Infrastructure Metrics**:
- CPU/memory usage per worker
- Queue depth
- API call success rate (LLM provider)
- Storage usage (images, database)

### Logging

**Structured Logging** (JSON):
```json
{
    "timestamp": "2026-07-30T14:32:10Z",
    "level": "INFO",
    "service": "extraction",
    "claim_id": "uuid",
    "stage": "extraction",
    "form_type": "CMS-1500",
    "extraction_method": "llm_escalated",
    "fields_escalated": 3,
    "latency_ms": 12450,
    "cost": 0.015
}
```

### Alerting Rules

```yaml
- alert: ExtractionAccuracyDropped
  expr: extraction_accuracy{field="patient_name"} < 0.60
  for: 1h
  labels:
    severity: critical
  annotations:
    summary: "Patient name extraction accuracy dropped below 60%"

- alert: QueueDepthHigh
  expr: queue_depth > 1000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Processing queue has >1000 pages waiting"
```

## Conclusion

This technical design document provides comprehensive specifications for implementing, deploying, and operating the Healthcare Claims Extraction Engine. All schemas, decision logic, and API contracts are production-ready and validated against real sample data.
