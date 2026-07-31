"""
Acceptance-criteria tests for the ground truth parser (Depth Pass 1).

These counts were verified by direct inspection of the real sample files before any code was
written (see project spec, Section 3) — they are not arbitrary, they are the ground truth for
the ground-truth parser itself.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from ground_truth.ground_truth_parser import build_spec_maps, parse_ground_truth_file

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NSF_SPEC = DATA_DIR / "specs" / "NSF_Matrix.txt"
UB92_SPEC = DATA_DIR / "specs" / "UB92_File_Specs.txt"


@pytest.fixture(scope="module")
def spec_maps():
    return build_spec_maps(NSF_SPEC, UB92_SPEC)


def test_group_a_has_exactly_12_claims(spec_maps):
    nsf_spec, _ = spec_maps
    path = DATA_DIR / "raw" / "Group A" / "DATAMATICS_UBH_HCFA_07212026 - Group A.txt"
    claims = parse_ground_truth_file(path, nsf_spec=nsf_spec, file_format="nsf")
    assert len(claims) == 12


def test_group_b_has_exactly_5_claims(spec_maps):
    nsf_spec, _ = spec_maps
    path = DATA_DIR / "raw" / "Group B" / "DATAMATICS_UBH_HCFA_07202026 - Group B.txt"
    claims = parse_ground_truth_file(path, nsf_spec=nsf_spec, file_format="nsf")
    assert len(claims) == 5


def test_group_c_has_exactly_6_claims(spec_maps):
    _, ub92_spec = spec_maps
    path = DATA_DIR / "raw" / "Group C" / "DATAMATICS_UBH_UB_07202026 - Group C.txt"
    claims = parse_ground_truth_file(path, ub92_spec=ub92_spec, file_format="ub92")
    assert len(claims) == 6


def test_group_d_has_exactly_7_claim_headers(spec_maps):
    nsf_spec, _ = spec_maps
    path = DATA_DIR / "raw" / "Group D" / "DATAMATICS_UBH_HCFA_07212026 - Group D.txt"
    claims = parse_ground_truth_file(path, nsf_spec=nsf_spec, file_format="nsf")
    assert len(claims) == 7


def test_group_a_first_claim_matches_known_patient(spec_maps):
    """Known from direct visual inspection of M047FJFL.001: patient is KARNO, YOLANA."""
    nsf_spec, _ = spec_maps
    path = DATA_DIR / "raw" / "Group A" / "DATAMATICS_UBH_HCFA_07212026 - Group A.txt"
    claims = parse_ground_truth_file(path, nsf_spec=nsf_spec, file_format="nsf")
    ca0 = claims[0]["records"]["CA0"][0]
    assert ca0["04.0_patient_last_name"] == "KARNO"
    assert ca0["05.0_patient_first_name"] == "YOLANA"


def test_group_c_first_claim_matches_known_patient(spec_maps):
    """Known from direct visual inspection of M047IJBF.001: patient is Daniels, Dameon."""
    _, ub92_spec = spec_maps
    path = DATA_DIR / "raw" / "Group C" / "DATAMATICS_UBH_UB_07202026 - Group C.txt"
    claims = parse_ground_truth_file(path, ub92_spec=ub92_spec, file_format="ub92")
    rec20 = claims[0]["records"]["20"][0]
    assert rec20["04_patient_last_name"] == "DANIELS"
    assert rec20["05_patient_first_name"] == "DAMEON"


def test_no_crash_on_malformed_input(spec_maps, tmp_path):
    """A garbage/empty file must return an empty list, never raise."""
    nsf_spec, _ = spec_maps
    bad_file = tmp_path / "garbage.txt"
    bad_file.write_text("this is not a valid ground truth file\n\x00\x01binary junk", encoding="utf-8")
    claims = parse_ground_truth_file(bad_file, nsf_spec=nsf_spec, file_format="nsf")
    assert claims == []  # no BA0 boundary found, so zero claims — not a crash
