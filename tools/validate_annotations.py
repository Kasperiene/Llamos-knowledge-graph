#!/usr/bin/env python3
"""Validate annotation JSON files against schema v2.0.

Checks structure, enum values, provenance consistency, and Claim rules.
Does NOT compute accuracy — that requires comparison against the PDF.

Usage:
    python tools/validate_annotations.py
    python tools/validate_annotations.py --dir data/annotations --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = "2.0"
SCHEMA_FILE = Path(__file__).parent.parent / "data/annotations/schema.json"

VALID_STATUS = {"pending", "reported", "not_reported", "not_applicable", "ambiguous"}
VALID_ORIGIN = {"human", "model", "human_revised", "final_reconciled"}
VALID_REVIEW  = {"unreviewed", "reviewed", "verified"}
VALID_PAPER_TYPE = {
    "quantitative_empirical", "qualitative_empirical", "mixed_methods",
    "scale_validation", "theoretical", "review", "other",
}
VALID_PUB_VERSION = {"published", "preprint", "postprint", "accepted_manuscript", "unknown"}
VALID_ROLES = {
    "independent", "dependent", "mediator", "moderator", "predictor",
    "outcome", "focal", "control", "psychometric_target", "not_applicable",
}
VALID_ITEM_TYPE = {"hypothesis", "research_question", "proposition", "exploratory", "post_hoc"}
VALID_FINDING_TYPE = {"main_result", "methodological", "theoretical", "practical", "limitation", "future_direction"}

EMPIRICAL_TYPES = {"quantitative_empirical", "qualitative_empirical", "mixed_methods", "scale_validation"}


@dataclass
class ValidationResult:
    file: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pending_count: int = 0
    review_status: str = "unknown"
    origin: str = "unknown"

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def ready_for_use(self) -> bool:
        return self.valid and self.review_status in ("reviewed", "verified")


def _check_claim(obj: object, path: str) -> tuple[list[str], list[str], int]:
    """Returns (errors, warnings, pending_count) for a Claim object."""
    errors, warnings = [], []
    pending = 0

    if not isinstance(obj, dict):
        return [f"{path}: expected Claim object, got {type(obj).__name__}"], [], 0

    status = obj.get("status")
    if status not in VALID_STATUS:
        errors.append(f"{path}.status: invalid value '{status}'")
        return errors, warnings, pending

    if status == "pending":
        pending += 1
        warnings.append(f"{path}: still pending")

    if status == "reported":
        has_provenance = (
            (isinstance(obj.get("quote"), str) and obj["quote"].strip()) or
            isinstance(obj.get("page"), int) or
            (isinstance(obj.get("section"), str) and obj["section"].strip())
        )
        if not has_provenance:
            errors.append(
                f"{path}: status=reported but no quote, page, or section provided"
            )
        if obj.get("value") is None:
            errors.append(f"{path}: status=reported but value is null")

    return errors, warnings, pending


def _check_construct(obj: dict, path: str) -> tuple[list[str], list[str], int]:
    errors, warnings, pending = [], [], 0

    role = obj.get("role")
    if role not in VALID_ROLES:
        errors.append(f"{path}.role: invalid value '{role}'")

    for claim_field in ("name", "measure_name", "items_n", "reliability"):
        val = obj.get(claim_field)
        if val is not None:
            e, w, p = _check_claim(val, f"{path}.{claim_field}")
            errors += e; warnings += w; pending += p

    return errors, warnings, pending


def _check_hypothesis(obj: dict, path: str) -> tuple[list[str], list[str], int]:
    errors, warnings, pending = [], [], 0

    if not obj.get("id"):
        errors.append(f"{path}: missing 'id'")

    stmt = obj.get("statement")
    if stmt is not None:
        e, w, p = _check_claim(stmt, f"{path}.statement")
        errors += e; warnings += w; pending += p

    result = obj.get("result")
    if result is not None:
        e, w, p = _check_claim(result, f"{path}.result")
        errors += e; warnings += w; pending += p

    item_type = obj.get("item_type")
    if item_type is not None and item_type not in VALID_ITEM_TYPE:
        errors.append(f"{path}.item_type: invalid value '{item_type}'")

    return errors, warnings, pending


def _check_study(obj: dict, path: str) -> tuple[list[str], list[str], int]:
    errors, warnings, pending = [], [], 0

    if not obj.get("study_id"):
        errors.append(f"{path}: missing 'study_id'")

    design = obj.get("design", {})
    for claim_field in ("methodology", "study_type", "data_collection", "country"):
        val = design.get(claim_field)
        if val is not None:
            e, w, p = _check_claim(val, f"{path}.design.{claim_field}")
            errors += e; warnings += w; pending += p

    sample = obj.get("sample", {})
    for claim_field in ("total_n", "population", "age_mean", "age_range", "gender_percent_female"):
        val = sample.get(claim_field)
        if val is not None:
            e, w, p = _check_claim(val, f"{path}.sample.{claim_field}")
            errors += e; warnings += w; pending += p

    for i, construct in enumerate(obj.get("constructs", [])):
        e, w, p = _check_construct(construct, f"{path}.constructs[{i}]")
        errors += e; warnings += w; pending += p

    for i, hyp in enumerate(obj.get("hypotheses", [])):
        e, w, p = _check_hypothesis(hyp, f"{path}.hypotheses[{i}]")
        errors += e; warnings += w; pending += p

    return errors, warnings, pending


def validate_file(path: Path) -> ValidationResult:
    result = ValidationResult(file=path.name)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        result.errors.append(f"JSON parse error: {e}")
        return result

    # schema_version
    ver = data.get("schema_version")
    if ver != SCHEMA_VERSION:
        result.errors.append(
            f"schema_version: expected '{SCHEMA_VERSION}', got '{ver}'. "
            f"Run: python tools/migrate_annotations.py"
        )
        return result

    # annotation_provenance
    prov = data.get("annotation_provenance")
    if not isinstance(prov, dict):
        result.errors.append("annotation_provenance: missing or not an object")
    else:
        origin = prov.get("origin", "")
        review = prov.get("review_status", "")
        result.origin = origin
        result.review_status = review

        if origin not in VALID_ORIGIN:
            result.errors.append(f"annotation_provenance.origin: invalid value '{origin}'")
        if review not in VALID_REVIEW:
            result.errors.append(f"annotation_provenance.review_status: invalid value '{review}'")

        if origin == "model" and review == "verified":
            result.errors.append(
                "annotation_provenance: origin=model cannot have review_status=verified. "
                "A human must review the annotation first."
            )
        if not prov.get("created_by"):
            result.errors.append("annotation_provenance.created_by: empty")
        if not prov.get("created_date"):
            result.errors.append("annotation_provenance.created_date: empty")

        if origin in ("model", "human_revised") and not prov.get("model_id"):
            result.warnings.append(
                "annotation_provenance.model_id: not set for model/human_revised origin"
            )
        if review in ("reviewed", "verified") and not prov.get("reviewed_by"):
            result.warnings.append(
                "annotation_provenance.reviewed_by: not set for reviewed/verified status"
            )

    # metadata
    meta = data.get("metadata", {})
    if not isinstance(meta, dict):
        result.errors.append("metadata: missing or not an object")
    else:
        for claim_field in ("title", "authors", "year", "journal", "doi"):
            val = meta.get(claim_field)
            if val is None:
                result.errors.append(f"metadata.{claim_field}: missing")
            else:
                e, w, p = _check_claim(val, f"metadata.{claim_field}")
                result.errors += e; result.warnings += w; result.pending_count += p

        pt = meta.get("paper_type_profile")
        if pt not in VALID_PAPER_TYPE:
            result.errors.append(f"metadata.paper_type_profile: invalid value '{pt}'")

        pv = meta.get("publication_version")
        if pv not in VALID_PUB_VERSION:
            result.errors.append(f"metadata.publication_version: invalid value '{pv}'")

    paper_type = meta.get("paper_type_profile", "")

    # studies
    studies = data.get("studies", [])
    if not isinstance(studies, list):
        result.errors.append("studies: must be an array")
    else:
        if paper_type in EMPIRICAL_TYPES and len(studies) == 0:
            result.warnings.append(
                f"studies[]: empty for paper_type={paper_type}. Add at least one study entry."
            )
        for i, study in enumerate(studies):
            e, w, p = _check_study(study, f"studies[{i}]")
            result.errors += e; result.warnings += w; result.pending_count += p

    # key_findings
    findings = data.get("key_findings", [])
    if not isinstance(findings, list):
        result.errors.append("key_findings: must be an array")
    else:
        if len(findings) == 0:
            result.warnings.append("key_findings: empty — add 3–6 findings")
        for i, f_item in enumerate(findings):
            if not isinstance(f_item, dict):
                result.errors.append(f"key_findings[{i}]: must be an object")
                continue
            if not f_item.get("statement"):
                result.errors.append(f"key_findings[{i}].statement: empty")
            ft = f_item.get("finding_type")
            if ft is not None and ft not in VALID_FINDING_TYPE:
                result.errors.append(f"key_findings[{i}].finding_type: invalid value '{ft}'")

    # theoretical_framework
    tf = data.get("theoretical_framework", [])
    if not isinstance(tf, list):
        result.errors.append("theoretical_framework: must be an array")
    elif len(tf) == 0 and paper_type not in ("other",):
        result.warnings.append("theoretical_framework: empty — add named theories")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="data/annotations")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--fail-on-error", action="store_true",
                        help="Exit with code 1 if any file has errors")
    args = parser.parse_args()

    ann_dir = Path(args.dir)
    files = sorted(ann_dir.glob("*.json"))
    NON_ANNOTATION = {"schema.json", "pilot_manifest.json"}
    files = [f for f in files if f.name not in NON_ANNOTATION]

    if not files:
        print(f"No annotation files found in {ann_dir}")
        sys.exit(0)

    results = [validate_file(f) for f in files]

    # Summary table
    W = 56
    print(f"\n{'FILE':<{W}} {'VALID':>5}  {'ORIGIN':<18}  {'REVIEW':<12}  PENDING  ISSUES")
    print("─" * 110)
    for r in results:
        valid_str  = "OK" if r.valid else f"ERR({len(r.errors)})"
        warn_str   = f"W{len(r.warnings)}" if r.warnings else ""
        issues_str = f"{valid_str} {warn_str}".strip()
        print(
            f"{r.file:<{W}} {valid_str:>5}  {r.origin:<18}  {r.review_status:<12}  "
            f"{r.pending_count:>7}  {warn_str}"
        )

    n_valid = sum(1 for r in results if r.valid)
    n_ready = sum(1 for r in results if r.ready_for_use)
    n_pending_total = sum(r.pending_count for r in results)

    print(f"\nStructurally valid : {n_valid}/{len(results)}")
    print(f"Ready for use      : {n_ready}/{len(results)}  (valid + reviewed/verified)")
    print(f"Pending fields     : {n_pending_total} total across all files")
    print()
    print("NOTE: 'valid' means the JSON structure is correct, NOT that the content is accurate.")
    print("      Accuracy requires comparing each claim against the source PDF.")

    if args.verbose or any(not r.valid for r in results):
        for r in results:
            if r.errors or (args.verbose and r.warnings):
                print(f"\n── {r.file}")
                for e in r.errors:
                    print(f"   ERROR   {e}")
                for w in r.warnings:
                    print(f"   WARN    {w}")

    if args.fail_on_error and not all(r.valid for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
