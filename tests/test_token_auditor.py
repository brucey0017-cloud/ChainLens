import pytest

from token_auditor import (
    build_report_filename,
    calculate_risk_score,
    extract_data_list,
    extract_data_obj,
    safe_float,
    safe_int,
    validate_inputs,
)


def test_validate_inputs_accepts_valid_values():
    validate_inputs("0x1234567890abcdef1234567890abcdef12345678", "ethereum")


def test_validate_inputs_rejects_bad_chain():
    with pytest.raises(ValueError):
        validate_inputs("0x1234567890abcdef1234567890abcdef12345678", "ETHEREUM!!!")


def test_validate_inputs_rejects_bad_address():
    with pytest.raises(ValueError):
        validate_inputs("../../etc/passwd", "solana")


def test_safe_numeric_helpers():
    assert safe_float("1.23") == 1.23
    assert safe_float("not-a-number", 7.0) == 7.0
    assert safe_int("42") == 42
    assert safe_int("bad", 9) == 9


def test_extract_data_helpers_shape_drift():
    assert extract_data_obj(None) == {}
    assert extract_data_obj({"data": []}) == {}
    assert extract_data_obj({"data": [{"x": 1}]}) == {"x": 1}
    assert extract_data_list(None) == []
    assert extract_data_list({"data": {"x": 1}}) == []
    assert extract_data_list({"data": [{"x": 1}, "bad", {"y": 2}]}) == [{"x": 1}, {"y": 2}]


def test_calculate_risk_score_missing_payloads_no_crash():
    score, factors = calculate_risk_score(None, None, None, None, None)
    assert isinstance(score, int)
    assert isinstance(factors, list)
    assert score >= 0


def test_report_filename_is_sanitized():
    path = build_report_filename("../../evil\\token?", "solana;rm -rf /", "20260318_020000")
    name = path.name
    assert ".." not in name
    assert "/" not in name
    assert "\\" not in name
    assert name.startswith("chainlens_report_solanarm-rf_")
    assert name.endswith("_20260318_020000.md")
