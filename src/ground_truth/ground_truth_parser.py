"""
ground_truth_parser.py

Parses a DATAMATICS ground-truth export file (NSF/HCFA or UB-92 fixed-width format) into a
list of structured per-claim dicts, using the field-position maps built by spec_parser.py.

Claim boundaries:
  - NSF/HCFA: a new claim starts at each 'BA0' line (verified: Group A has 12 BA0 lines = 12
    claims; Group D has 7 BA0 lines = 7 claim headers).
  - UB-92: a new claim starts at each '10' line (verified: Group C has 6 '10' lines = 6 claims).

Never crashes: unknown record-type prefixes, blank lines, or lines with no matching spec are
logged and skipped, not raised. A malformed line never stops the rest of the file from parsing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from ground_truth.spec_parser import RecordSpec, extract_record_fields, parse_spec_file

logger = logging.getLogger(__name__)

FileFormat = Literal["nsf", "ub92"]

NSF_CLAIM_BOUNDARY_RECORD = "BA0"
UB92_CLAIM_BOUNDARY_RECORD = "10"


def detect_file_format(path: str | Path) -> FileFormat:
    """Best-effort detection from filename convention; falls back to content sniffing."""
    name = Path(path).name.upper()
    if "HCFA" in name:
        return "nsf"
    if "_UB_" in name or name.endswith("UB.TXT") or "UB92" in name:
        return "ub92"

    # Fallback: sniff the first non-empty line's record-type prefix.
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.strip():
                    return "nsf" if line[:3].isalpha() or line[:3] == "AA0" else "ub92"
    except OSError as exc:
        logger.warning("Could not sniff file format for %s: %s", path, exc)
    return "nsf"


def _record_type_key(line: str, file_format: FileFormat) -> str:
    return line[:3].strip() if file_format == "nsf" else line[:2].strip()


def parse_ground_truth_file(
    path: str | Path,
    nsf_spec: dict[str, RecordSpec] | None = None,
    ub92_spec: dict[str, RecordSpec] | None = None,
    file_format: FileFormat | None = None,
) -> list[dict]:
    """
    Parse one ground-truth export file into a list of per-claim dicts.

    Each claim dict has shape: {"claim_index": int, "records": {record_type: [field_dict, ...]}}
    Repeating record types (e.g. FA0 service lines, UB-92 60/61 revenue lines) collect into a
    list in encounter order; single-occurrence record types still use a one-item list for
    consistency.
    """
    path = Path(path)
    fmt = file_format or detect_file_format(path)
    boundary = NSF_CLAIM_BOUNDARY_RECORD if fmt == "nsf" else UB92_CLAIM_BOUNDARY_RECORD

    spec_map = nsf_spec if fmt == "nsf" else ub92_spec
    if spec_map is None:
        logger.error("No spec map provided for format %s; cannot parse %s", fmt, path)
        return []

    try:
        raw_lines = path.read_text(encoding="utf-8", errors="ignore").split("\n")
    except OSError as exc:
        logger.error("Could not read ground truth file %s: %s", path, exc)
        return []

    claims: list[dict] = []
    current_claim: dict | None = None

    for line_no, line in enumerate(raw_lines, start=1):
        if not line.strip():
            continue

        record_type = _record_type_key(line, fmt)
        if not record_type:
            continue

        if record_type == boundary:
            current_claim = {"claim_index": len(claims), "records": {}}
            claims.append(current_claim)

        if current_claim is None:
            # Lines before the first claim boundary (file/batch header records) are skipped
            # for per-claim purposes but never crash the parse.
            continue

        record_spec = spec_map.get(record_type)
        if record_spec is None or not record_spec.fields:
            # Unknown or "currently not used" record type for this line — log and move on.
            logger.debug("Line %d: no field spec for record type '%s', skipping", line_no, record_type)
            continue

        try:
            extracted = extract_record_fields(line, record_spec)
        except Exception as exc:  # never let one bad line kill the whole parse
            logger.warning("Line %d: failed to extract fields for '%s': %s", line_no, record_type, exc)
            continue

        current_claim["records"].setdefault(record_type, []).append(extracted)

    return claims


def build_spec_maps(nsf_path: str | Path, ub92_path: str | Path) -> tuple[dict, dict]:
    """Convenience loader: parse both spec files once, reuse across many ground-truth files."""
    return parse_spec_file(nsf_path), parse_spec_file(ub92_path)
