"""Targeted tests for annotation schema v2.1 validation and migration rules.

Run: pytest tests/test_annotations.py -v
"""
import json
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from validate_annotations import (
    validate_file, ValidationResult, check_claim,
    CURRENT_VERSION,
)
from migrate_annotations import (
    normalize_paper_id, migrate_one, migrate_v20_to_v21,
    _infer_origin_v1,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _claim(value=None, status="pending", quote=None, page=None, section=None):
    return {"value": value, "status": status, "quote": quote,
            "page": page, "section": section, "fragment_id": None}


def _base_v21(paper_type="theoretical", created_date="2026-01-01", origin="human"):
    """Minimal valid v2.1 annotation (no studies, no findings — theoretical paper)."""
    return {
        "paper_id": "test_paper_2026",
        "schema_version": "2.1",
        "annotation_provenance": {
            "origin": origin,
            "review_status": "verified",
            "created_by": "Test Annotator",
            "created_date": created_date,
            "model_id": None,
            "reviewed_by": "Test Reviewer",
            "reviewed_date": "2026-01-02",
            "human_read_time_minutes": 30,
            "model_run_time_seconds": None,
            "correction_time_minutes": None,
            "legacy_time_minutes": None,
        },
        "metadata": {
            "title":   _claim("Test Title", "reported", "Test Title appears on page 1"),
            "authors": _claim(["Smith, J."], "reported", "J. Smith is listed as author"),
            "year":    _claim(2026, "reported", "Published 2026"),
            "journal": _claim("Test Journal", "reported", "Published in Test Journal"),
            "doi":     _claim("10.1234/test", "reported", "DOI: 10.1234/test"),
            "paper_type_profile": paper_type,
            "publication_version": "published",
        },
        "studies": [],
        "key_findings": [
            {"statement": "Finding 1.", "status": "reported",
             "finding_type": "main_result", "quote": "Finding 1 verbatim.", "page": 5, "section": "Results"}
        ],
        "theoretical_framework": [
            {"name": "Social Identity Theory", "status": "reported",
             "quote": "Drawing on Social Identity Theory...", "page": 2, "section": "Theory"}
        ],
        "notes": "",
    }


def _validate(data: dict) -> ValidationResult:
    """Write to temp file and validate it."""
    import tempfile, os
    schema = json.loads((ROOT / "data/annotations/schema.json").read_text(encoding="utf-8"))
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                    delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        name = f.name
    try:
        return validate_file(Path(name), schema)
    finally:
        os.unlink(name)


# ── Claim validation ────────────────────────────────────────────────────────

class TestClaimValidation:

    def test_reported_requires_quote(self):
        res = ValidationResult(file="test")
        check_claim(_claim("some value", "reported", quote=None), "field", res)
        assert any("quote" in e for e in res.errors), \
            "reported without quote should produce an error"

    def test_reported_with_quote_ok(self):
        res = ValidationResult(file="test")
        check_claim(_claim("some value", "reported", quote="verbatim text"), "field", res)
        assert not res.errors

    def test_reported_with_page_only_fails(self):
        """Page is localisation, not evidence — reported still requires quote."""
        res = ValidationResult(file="test")
        check_claim(_claim("val", "reported", quote=None, page=3), "field", res)
        assert any("quote" in e for e in res.errors)

    def test_ambiguous_requires_quote(self):
        res = ValidationResult(file="test")
        check_claim(_claim("unclear", "ambiguous", quote=None), "field", res)
        assert any("quote" in e for e in res.errors)

    def test_not_reported_no_quote_needed(self):
        res = ValidationResult(file="test")
        check_claim(_claim(None, "not_reported"), "field", res)
        assert not res.errors

    def test_pending_adds_to_pending_list(self):
        res = ValidationResult(file="test")
        check_claim(_claim(None, "pending"), "field", res)
        assert "field" in res.pending_fields
        assert not res.errors

    def test_page_must_be_positive_integer(self):
        res = ValidationResult(file="test")
        check_claim(_claim("val", "reported", quote="x", page=0), "field", res)
        assert any("page" in e for e in res.errors)

    def test_page_negative_fails(self):
        res = ValidationResult(file="test")
        check_claim(_claim("val", "reported", quote="x", page=-1), "field", res)
        assert any("page" in e for e in res.errors)

    def test_invalid_status_fails(self):
        res = ValidationResult(file="test")
        check_claim(_claim("val", "yes"), "field", res)
        assert res.errors


# ── Annotation-level validation ─────────────────────────────────────────────

class TestAnnotationLevel:

    def test_model_origin_cannot_be_verified(self):
        data = _base_v21(origin="model")
        data["annotation_provenance"]["review_status"] = "verified"
        res = _validate(data)
        assert any("model" in e and "verified" in e for e in res.errors)

    def test_human_verified_no_pending_is_ground_truth_ready(self):
        data = _base_v21(origin="human")
        res = _validate(data)
        assert res.level == "GROUND_TRUTH_READY", \
            f"Expected GROUND_TRUTH_READY, got {res.level}. Errors: {res.errors}"

    def test_pending_fields_block_ground_truth(self):
        data = _base_v21()
        data["metadata"]["title"] = _claim(None, "pending")
        res = _validate(data)
        assert res.level != "GROUND_TRUTH_READY"
        assert any("pending" in b for b in res.ground_truth_blocked)

    def test_template_has_no_created_date(self):
        data = _base_v21(created_date="")
        res = _validate(data)
        assert res.is_template
        assert res.level == "TEMPLATE"

    def test_wrong_schema_version_is_error(self):
        data = _base_v21()
        data["schema_version"] = "2.0"
        res = _validate(data)
        assert res.errors
        assert any("schema_version" in e for e in res.errors)

    def test_unknown_origin_blocks_ground_truth(self):
        data = _base_v21(origin="unknown")
        res = _validate(data)
        assert res.level != "GROUND_TRUTH_READY"

    def test_key_finding_reported_requires_quote(self):
        data = _base_v21()
        data["key_findings"][0]["status"] = "reported"
        data["key_findings"][0]["quote"] = None
        res = _validate(data)
        assert any("quote" in e for e in res.errors)

    def test_theoretical_ref_reported_requires_quote(self):
        data = _base_v21()
        data["theoretical_framework"][0]["status"] = "reported"
        data["theoretical_framework"][0]["quote"] = None
        res = _validate(data)
        assert any("quote" in e for e in res.errors)


# ── Migration ────────────────────────────────────────────────────────────────

class TestMigration:

    def test_paper_id_curly_quotes_normalized(self):
        raw = "Fransen et al. - 2022 - Unlocking the power of ‘us’ Longitudinal"
        normalized = normalize_paper_id(raw)
        assert '‘' not in normalized
        assert '’' not in normalized
        assert "'us'" in normalized  # replaced with straight quotes

    def test_model_run_time_not_from_minutes(self):
        """v2.0 annotation with model_run_time_seconds (wrongly set from minutes) → v2.1 moves to legacy."""
        v20 = {
            "paper_id": "test",
            "schema_version": "2.0",
            "annotation_provenance": {
                "origin": "model", "review_status": "unreviewed",
                "created_by": "Claude", "created_date": "2026-01-01",
                "model_id": "claude-3", "reviewed_by": None, "reviewed_date": None,
                "human_read_time_minutes": None,
                "model_run_time_seconds": 10,  # incorrectly set from old annotation_time_minutes
                "correction_time_minutes": None,
            },
            "metadata": {
                "title": _claim(), "authors": _claim(), "year": _claim(2020),
                "journal": _claim(), "doi": _claim(),
                "paper_type_profile": "theoretical", "publication_version": "unknown",
            },
            "studies": [], "key_findings": [], "theoretical_framework": [], "notes": "",
        }
        v21 = migrate_v20_to_v21(v20)
        prov = v21["annotation_provenance"]
        assert prov["model_run_time_seconds"] is None, \
            "model_run_time_seconds should be null — old value was minutes, not seconds"
        assert prov["legacy_time_minutes"] == 10, \
            "Old value should be preserved as legacy_time_minutes"

    def test_theoretical_framework_strings_converted_to_objects(self):
        v20 = {
            "paper_id": "test",
            "schema_version": "2.0",
            "annotation_provenance": {
                "origin": "human", "review_status": "unreviewed",
                "created_by": "Test", "created_date": "2026-01-01",
                "model_id": None, "reviewed_by": None, "reviewed_date": None,
                "human_read_time_minutes": None, "model_run_time_seconds": None,
                "correction_time_minutes": None,
            },
            "metadata": {
                "title": _claim(), "authors": _claim(), "year": _claim(2020),
                "journal": _claim(), "doi": _claim(),
                "paper_type_profile": "theoretical", "publication_version": "unknown",
            },
            "studies": [], "key_findings": [],
            "theoretical_framework": ["Social Identity Theory", "Self-Categorization Theory"],
            "notes": "",
        }
        v21 = migrate_v20_to_v21(v20)
        tf = v21["theoretical_framework"]
        assert all(isinstance(item, dict) for item in tf)
        assert tf[0]["name"] == "Social Identity Theory"
        assert tf[0]["status"] == "pending"

    def test_key_findings_get_status_field(self):
        v20 = {
            "paper_id": "test",
            "schema_version": "2.0",
            "annotation_provenance": {
                "origin": "model", "review_status": "unreviewed",
                "created_by": "Claude", "created_date": "2026-01-01",
                "model_id": "claude-3", "reviewed_by": None, "reviewed_date": None,
                "human_read_time_minutes": None, "model_run_time_seconds": None,
                "correction_time_minutes": None,
            },
            "metadata": {
                "title": _claim(), "authors": _claim(), "year": _claim(),
                "journal": _claim(), "doi": _claim(),
                "paper_type_profile": "theoretical", "publication_version": "unknown",
            },
            "studies": [],
            "key_findings": [
                {"statement": "Finding 1.", "finding_type": "main_result",
                 "quote": None, "page": None, "section": None}
            ],
            "theoretical_framework": [],
            "notes": "",
        }
        v21 = migrate_v20_to_v21(v20)
        assert v21["key_findings"][0].get("status") == "pending"

    def test_empty_annotator_gives_unknown_origin(self):
        origin = _infer_origin_v1("")
        assert origin == "unknown"

    def test_nonempty_human_name_gives_human_origin(self):
        assert _infer_origin_v1("Rimante Kasperiene") == "human"

    def test_model_name_gives_model_origin(self):
        assert _infer_origin_v1("Claude (example)") == "model"
        assert _infer_origin_v1("GPT-4") == "model"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
