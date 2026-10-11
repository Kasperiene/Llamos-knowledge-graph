#!/usr/bin/env python3
"""Validate annotation files against schema v2.1.

Three annotation levels:
  TEMPLATE        — file exists but annotator has not started (no created_date)
  IN_PROGRESS     — annotator has started; may have structural errors or pending fields
  STRUCTURALLY_VALID — passes all structural checks; may still have pending fields
  GROUND_TRUTH_READY — no structural errors, no pending fields, review_status=verified,
                        origin != model  ← only this level can serve as ground truth

'Valid' means JSON structure is correct. It does NOT mean the content is accurate.
Accuracy requires comparing each claim against the source PDF.

Usage:
    python tools/validate_annotations.py
    python tools/validate_annotations.py --dir data/annotations --verbose
    python tools/validate_annotations.py --fail-on-error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import jsonschema
    _JSONSCHEMA = True
except ImportError:
    _JSONSCHEMA = False

SCHEMA_FILE  = Path(__file__).parent.parent / "data/annotations/schema.json"
NON_ANNOTATION = {"schema.json", "pilot_manifest.json"}
CURRENT_VERSION = "2.1"

VALID_STATUS  = {"pending", "reported", "not_reported", "not_applicable", "ambiguous"}
VALID_ORIGIN  = {"human", "model", "human_revised", "final_reconciled", "unknown"}
VALID_REVIEW  = {"unreviewed", "reviewed", "verified"}
VALID_PT      = {"quantitative_empirical", "qualitative_empirical", "mixed_methods",
                 "scale_validation", "theoretical", "review", "other"}
VALID_PV      = {"published", "preprint", "postprint", "accepted_manuscript", "unknown"}
VALID_ROLES   = {"independent", "dependent", "mediator", "moderator", "predictor",
                 "outcome", "focal", "control", "psychometric_target", "not_applicable"}
VALID_ITEM    = {"hypothesis", "research_question", "proposition", "exploratory", "post_hoc", None}
VALID_FTYPE   = {"main_result", "methodological", "theoretical", "practical",
                 "limitation", "future_direction", None}
EMPIRICAL     = {"quantitative_empirical", "qualitative_empirical", "mixed_methods", "scale_validation"}

# Statuses that require a non-empty quote
QUOTE_REQUIRED = {"reported", "ambiguous"}


@dataclass
class ValidationResult:
    file: str
    errors: list[str]   = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pending_fields: list[str] = field(default_factory=list)

    origin: str = "unknown"
    review_status: str = "unknown"
    is_template: bool = False

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def level(self) -> str:
        if self.is_template:
            return "TEMPLATE"
        if not self.valid:
            return "IN_PROGRESS"
        if self.pending_fields:
            return "STRUCTURALLY_VALID"
        if (self.review_status == "verified"
                and self.origin not in ("model", "unknown")):
            return "GROUND_TRUTH_READY"
        return "STRUCTURALLY_VALID"

    @property
    def ground_truth_blocked(self) -> list[str]:
        reasons = []
        if self.pending_fields:
            reasons.append(f"{len(self.pending_fields)} pending field(s)")
        if self.errors:
            reasons.append(f"{len(self.errors)} structural error(s)")
        if self.review_status != "verified":
            reasons.append(f"review_status={self.review_status} (need verified)")
        if self.origin in ("model", "unknown"):
            reasons.append(f"origin={self.origin} (need human/human_revised/final_reconciled)")
        return reasons


# ── Claim-level checks ────────────────────────────────────────────────────

def check_claim(obj: object, path: str, res: ValidationResult) -> None:
    if not isinstance(obj, dict):
        res.errors.append(f"{path}: expected Claim object, got {type(obj).__name__}")
        return

    status = obj.get("status")
    if status not in VALID_STATUS:
        res.errors.append(f"{path}.status: invalid value '{status}'")
        return

    if status == "pending":
        res.pending_fields.append(path)

    if status in QUOTE_REQUIRED:
        quote = obj.get("quote")
        if not (isinstance(quote, str) and quote.strip()):
            res.errors.append(
                f"{path}: status='{status}' requires a non-empty quote "
                f"(page/section is localisation only, not evidence)"
            )
        if obj.get("value") is None:
            res.errors.append(f"{path}: status='{status}' but value is null")

    page = obj.get("page")
    if page is not None and (not isinstance(page, int) or page < 1):
        res.errors.append(f"{path}.page: must be a positive integer or null, got {page!r}")


def check_theoretical_ref(obj: object, path: str, res: ValidationResult) -> None:
    if not isinstance(obj, dict):
        res.errors.append(f"{path}: expected TheoreticalRef object, got {type(obj).__name__}")
        return
    if not obj.get("name"):
        res.errors.append(f"{path}.name: empty")
    status = obj.get("status")
    if status not in VALID_STATUS:
        res.errors.append(f"{path}.status: invalid value '{status}'")
    elif status == "pending":
        res.pending_fields.append(f"{path}.status")
    elif status in QUOTE_REQUIRED:
        quote = obj.get("quote")
        if not (isinstance(quote, str) and quote.strip()):
            res.errors.append(f"{path}: status='{status}' requires a non-empty quote")
    page = obj.get("page")
    if page is not None and (not isinstance(page, int) or page < 1):
        res.errors.append(f"{path}.page: must be a positive integer or null, got {page!r}")


def check_key_finding(obj: object, path: str, res: ValidationResult) -> None:
    if not isinstance(obj, dict):
        res.errors.append(f"{path}: expected KeyFinding object")
        return
    if not obj.get("statement"):
        res.errors.append(f"{path}.statement: empty")
    status = obj.get("status")
    if status not in VALID_STATUS:
        res.errors.append(f"{path}.status: invalid value '{status!r}'")
    elif status == "pending":
        res.pending_fields.append(f"{path}.status")
    elif status in QUOTE_REQUIRED:
        quote = obj.get("quote")
        if not (isinstance(quote, str) and quote.strip()):
            res.errors.append(f"{path}: status='{status}' requires a non-empty quote")
    ft = obj.get("finding_type")
    if ft not in VALID_FTYPE:
        res.errors.append(f"{path}.finding_type: invalid value '{ft}'")
    page = obj.get("page")
    if page is not None and (not isinstance(page, int) or page < 1):
        res.errors.append(f"{path}.page: must be positive integer or null")


def check_construct(obj: dict, path: str, res: ValidationResult) -> None:
    if obj.get("role") not in VALID_ROLES:
        res.errors.append(f"{path}.role: invalid value '{obj.get('role')}'")
    for cf in ("name", "measure_name", "items_n", "reliability"):
        val = obj.get(cf)
        if val is not None:
            check_claim(val, f"{path}.{cf}", res)


def check_hypothesis(obj: dict, path: str, res: ValidationResult) -> None:
    if not obj.get("id"):
        res.errors.append(f"{path}: missing id")
    for cf in ("statement", "result", "effect_size"):
        val = obj.get(cf)
        if val is not None:
            check_claim(val, f"{path}.{cf}", res)
    if obj.get("item_type") not in VALID_ITEM:
        res.errors.append(f"{path}.item_type: invalid value '{obj.get('item_type')}'")


def check_study(obj: dict, path: str, res: ValidationResult) -> None:
    if not obj.get("study_id"):
        res.errors.append(f"{path}: missing study_id")
    for cf in ("methodology", "study_type", "data_collection", "country"):
        val = (obj.get("design") or {}).get(cf)
        if val is not None:
            check_claim(val, f"{path}.design.{cf}", res)
    for cf in ("total_n", "population", "age_mean", "age_range", "gender_percent_female"):
        val = (obj.get("sample") or {}).get(cf)
        if val is not None:
            check_claim(val, f"{path}.sample.{cf}", res)
    for i, c in enumerate(obj.get("constructs", [])):
        check_construct(c, f"{path}.constructs[{i}]", res)
    for i, h in enumerate(obj.get("hypotheses", [])):
        check_hypothesis(h, f"{path}.hypotheses[{i}]", res)


# ── File-level validation ────────────────────────────────────────────────

def validate_file(path: Path, schema: dict | None) -> ValidationResult:
    res = ValidationResult(file=path.name)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        res.errors.append(f"JSON parse error: {e}")
        return res

    # Schema version check
    ver = data.get("schema_version")
    if ver != CURRENT_VERSION:
        res.errors.append(
            f"schema_version: expected '{CURRENT_VERSION}', got '{ver}'. "
            f"Run: python tools/migrate_annotations.py --write"
        )
        return res

    # jsonschema structural validation
    if _JSONSCHEMA and schema:
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            res.errors.append(f"Schema error at {e.json_path}: {e.message}")
        except jsonschema.SchemaError as e:
            res.warnings.append(f"Schema itself has an error: {e.message}")

    # annotation_provenance
    prov = data.get("annotation_provenance") or {}
    origin       = prov.get("origin", "")
    review_status = prov.get("review_status", "")
    res.origin       = origin
    res.review_status = review_status

    if origin not in VALID_ORIGIN:
        res.errors.append(f"annotation_provenance.origin: invalid '{origin}'")
    if review_status not in VALID_REVIEW:
        res.errors.append(f"annotation_provenance.review_status: invalid '{review_status}'")
    if origin == "model" and review_status == "verified":
        res.errors.append(
            "annotation_provenance: origin=model cannot have review_status=verified — "
            "a human must review and change origin to human_revised or final_reconciled"
        )
    if origin in ("model", "human_revised") and not prov.get("model_id"):
        res.warnings.append("annotation_provenance.model_id: not set for model/human_revised")
    if review_status in ("reviewed", "verified") and not prov.get("reviewed_by"):
        res.warnings.append("annotation_provenance.reviewed_by: not set for reviewed/verified")

    # Detect blank template (no created_date)
    if not prov.get("created_date"):
        res.is_template = True
        return res  # Skip further checks — template is expected to be empty

    # metadata Claims
    meta = data.get("metadata") or {}
    for cf in ("title", "authors", "year", "journal", "doi"):
        val = meta.get(cf)
        if val is None:
            res.errors.append(f"metadata.{cf}: missing")
        else:
            check_claim(val, f"metadata.{cf}", res)

    pt = meta.get("paper_type_profile")
    if pt not in VALID_PT:
        res.errors.append(f"metadata.paper_type_profile: invalid '{pt}'")
    if meta.get("publication_version") not in VALID_PV:
        res.errors.append(f"metadata.publication_version: invalid '{meta.get('publication_version')}'")

    # studies
    studies = data.get("studies") or []
    if pt in EMPIRICAL and not studies:
        res.warnings.append(f"studies[]: empty for paper_type={pt}")
    for i, s in enumerate(studies):
        check_study(s, f"studies[{i}]", res)

    # key_findings
    findings = data.get("key_findings") or []
    if not findings:
        res.warnings.append("key_findings: empty — add 3–6 findings")
    for i, f in enumerate(findings):
        check_key_finding(f, f"key_findings[{i}]", res)

    # theoretical_framework
    for i, tf in enumerate(data.get("theoretical_framework") or []):
        check_theoretical_ref(tf, f"theoretical_framework[{i}]", res)
    if not data.get("theoretical_framework") and pt not in ("other",):
        res.warnings.append("theoretical_framework: empty")

    return res


LEVEL_ORDER = {"TEMPLATE": 0, "IN_PROGRESS": 1, "STRUCTURALLY_VALID": 2, "GROUND_TRUTH_READY": 3}
LEVEL_COLOR = {"TEMPLATE": "·", "IN_PROGRESS": "!", "STRUCTURALLY_VALID": "✓", "GROUND_TRUTH_READY": "★"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="data/annotations")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    ann_dir  = Path(args.dir)
    schema   = None
    if _JSONSCHEMA and SCHEMA_FILE.exists():
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    elif not _JSONSCHEMA:
        print("WARNING: jsonschema not installed — skipping structural schema validation.\n"
              "Install with: pip install jsonschema\n")

    files = [f for f in sorted(ann_dir.glob("*.json")) if f.name not in NON_ANNOTATION]
    if not files:
        print(f"No annotation files found in {ann_dir}")
        sys.exit(0)

    results = [validate_file(f, schema) for f in files]

    # Summary table
    W = 58
    print(f"\n{'FILE':<{W}} {'LEVEL':<22}  {'ORIGIN':<18}  {'REVIEW':<12}  PENDING")
    print("─" * 120)
    for r in results:
        icon = LEVEL_COLOR.get(r.level, "?")
        level_str = f"{icon} {r.level}"
        print(f"{r.file:<{W}} {level_str:<22}  {r.origin:<18}  {r.review_status:<12}  {len(r.pending_fields)}")

    counts = {lv: sum(1 for r in results if r.level == lv) for lv in LEVEL_ORDER}
    print()
    print(f"  · TEMPLATE           : {counts['TEMPLATE']}")
    print(f"  ! IN_PROGRESS        : {counts['IN_PROGRESS']}")
    print(f"  ✓ STRUCTURALLY_VALID : {counts['STRUCTURALLY_VALID']}")
    print(f"  ★ GROUND_TRUTH_READY : {counts['GROUND_TRUTH_READY']}")
    print()
    print("NOTE: 'valid' = correct JSON structure. It does NOT mean content is accurate.")
    print("      Only GROUND_TRUTH_READY annotations may serve as evaluation ground truth.")
    print("      Accuracy requires human comparison against the source PDF.")

    if args.verbose or any(r.errors for r in results):
        for r in results:
            if r.errors or r.warnings or (args.verbose and r.pending_fields):
                print(f"\n── {r.file}")
                for e in r.errors:
                    print(f"   ERROR   {e}")
                for w in r.warnings:
                    print(f"   WARN    {w}")
                if args.verbose and r.pending_fields:
                    for p in r.pending_fields[:10]:
                        print(f"   PENDING {p}")
                    if len(r.pending_fields) > 10:
                        print(f"   PENDING ... ({len(r.pending_fields) - 10} more)")

                if r.ground_truth_blocked:
                    print(f"   BLOCKED: ground truth blocked — {'; '.join(r.ground_truth_blocked)}")

    if args.fail_on_error and any(r.errors for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
