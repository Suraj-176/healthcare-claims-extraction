"""
spec_parser.py

Parses the converted NSF Matrix and UB-92 fixed-width field specification text files into a
machine-readable field-position map. This is the foundation the ground-truth parser relies on:
positions are verified 1-indexed, first character of each record line = position 1.

Verified against real sample data: NSF Matrix field 04.0 (Patient Last Name, positions 23-42)
matches exactly where "KARNO" appears in a real CA0 ground-truth line from Group A.

Never crashes: any parsing failure for an individual record/field is logged and skipped, never
raised, so a spec-format quirk in one section can't take down the whole parse.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Matches "Record Type:\tXXX\tRecord Name:\t..." allowing for the optional stray space before
# the tab that appears in some sections of the converted .doc ("Record Type: \tCA0\t...").
RECORD_HEADER_RE = re.compile(
    r"Record Type:\s+([A-Z0-9]{2,3})\s*\t?\s*Record Name:\s*\t?\s*([^\n\t]*)"
)

# Matches a field definition row. NSF-style: "04.0\t23\t42\tX(20)\tR\tPatient Last Name".
# UB-92-style (no decimal): "04\t25\t44\tX(20)\tR\tPatient Last Name".
FIELD_ROW_RE = re.compile(
    r"^(\d{1,2}(?:\.\d)?)\t(\d{1,3})\t(\d{1,3})\t([^\t\n]*)\t([A-Z])\t([^\n]*)$",
    re.MULTILINE,
)


@dataclass
class FieldSpec:
    field_no: str
    position_from: int  # 1-indexed, inclusive
    position_to: int  # 1-indexed, inclusive
    picture: str
    requirement: str  # R=Required, C=Conditional, O=Optional, N=Not used
    description: str

    @property
    def length(self) -> int:
        return self.position_to - self.position_from + 1


@dataclass
class RecordSpec:
    record_type: str
    record_name: str
    fields: list[FieldSpec] = field(default_factory=list)


def parse_spec_file(path: str | Path) -> dict[str, RecordSpec]:
    """
    Parse a converted spec text file (NSF Matrix or UB-92 File Specs) into a dict of
    record_type -> RecordSpec. Never raises: unparseable sections are logged and skipped.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        logger.error("Could not read spec file %s: %s", path, exc)
        return {}

    headers = list(RECORD_HEADER_RE.finditer(text))
    if not headers:
        logger.warning("No record headers found in spec file %s", path)
        return {}

    records: dict[str, RecordSpec] = {}
    for i, header_match in enumerate(headers):
        record_type = header_match.group(1).strip()
        record_name = header_match.group(2).strip()

        section_start = header_match.end()
        section_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section_text = text[section_start:section_end]

        spec = records.setdefault(record_type, RecordSpec(record_type, record_name))

        for row_match in FIELD_ROW_RE.finditer(section_text):
            try:
                field_no, pos_from, pos_to, picture, req, desc = row_match.groups()
                spec.fields.append(
                    FieldSpec(
                        field_no=field_no,
                        position_from=int(pos_from),
                        position_to=int(pos_to),
                        picture=picture.strip(),
                        requirement=req.strip(),
                        description=desc.strip(),
                    )
                )
            except (ValueError, IndexError) as exc:
                logger.warning("Skipping unparseable field row in %s: %s", record_type, exc)
                continue

    return records


def extract_record_fields(line: str, record_spec: RecordSpec) -> dict:
    """
    Given a raw fixed-width ground-truth line and its matching RecordSpec, extract every field
    by its 1-indexed position range. Never raises: out-of-range positions (e.g. a short/
    truncated line) yield an empty string for that field rather than crashing.
    """
    result = {"record_type": record_spec.record_type}
    for f in record_spec.fields:
        try:
            # Convert 1-indexed inclusive [from, to] to Python 0-indexed slice.
            value = line[f.position_from - 1 : f.position_to].strip()
        except IndexError:
            value = ""
        key = f"{f.field_no}_{_slugify(f.description)}"
        result[key] = value
    return result


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:60] or "field"
