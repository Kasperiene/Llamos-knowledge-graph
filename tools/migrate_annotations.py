#!/usr/bin/env python3
"""Migrate annotation files from schema v1 (flat) to schema v2.0 (Claim-based).

All migrated values are wrapped as Claim objects with status=pending.
Annotation provenance is set to origin=model/human based on original annotator field.

Usage:
    python tools/migrate_annotations.py               # dry run
    python tools/migrate_annotations.py --write       # write migrated files
    python tools/migrate_annotations.py --write --backup  # keep .v1.bak originals
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
from pathlib import Path

ANN_DIR = Path(__file__).parent.parent / "data/annotations"
SCHEMA_VERSION = "2.0"

MODEL_ANNOTATOR_PATTERN = re.compile(r"claude|model|llm|gpt|gemini", re.IGNORECASE)


def _pending(value=None) -> dict:
    return {"value": value, "status": "pending", "quote": None, "page": None, "section": None, "fragment_id": None}


def _infer_provenance(old: dict) -> dict:
    annotator = old.get("annotator", "")
    is_model = bool(MODEL_ANNOTATOR_PATTERN.search(annotator))
    origin = "model" if is_model else "human"
    review_status = "unreviewed"

    return {
        "origin": origin,
        "review_status": review_status,
        "created_by": annotator or "unknown",
        "created_date": old.get("annotation_date") or "",
        "model_id": annotator if is_model else None,
        "reviewed_by": None,
        "reviewed_date": None,
        "human_read_time_minutes": None if is_model else old.get("annotation_time_minutes"),
        "model_run_time_seconds": old.get("annotation_time_minutes") if is_model else None,
        "correction_time_minutes": None,
    }


def _infer_pub_version(old: dict) -> str:
    notes = (old.get("notes") or "").lower()
    if "preprint" in notes:
        return "preprint"
    if "postprint" in notes or "accepted manuscript" in notes or "wrap" in notes:
        return "accepted_manuscript"
    return "unknown"


def _map_paper_type(old_type: str) -> str:
    mapping = {
        "empirical": "quantitative_empirical",
        "theoretical": "theoretical",
        "review": "review",
        "mixed": "mixed_methods",
        "qualitative": "qualitative_empirical",
        "scale_validation": "scale_validation",
    }
    return mapping.get((old_type or "").lower(), "other")


def _migrate_construct(c: dict) -> dict:
    old_type = c.get("type", "")
    role_map = {
        "IL": "focal", "SI": "focal", "leadership": "focal",
        "individual": "focal", "group": "focal", "other": "not_applicable",
    }
    role = role_map.get(old_type, "not_applicable")

    alpha = c.get("reliability_alpha")
    return {
        "name": _pending(c.get("name") or None),
        "role": role,
        "measure_name": _pending(c.get("measure") or None),
        "items_n": _pending(c.get("items") or None),
        "reliability": _pending(alpha),
        "reliability_type": "alpha" if alpha is not None else None,
        "psychometric_notes": None,
    }


def _migrate_hypothesis(h: dict) -> dict:
    supported = h.get("supported")
    if supported is True:
        result_val = "supported"
    elif supported is False:
        result_val = "not supported"
    else:
        result_val = None

    return {
        "id": h.get("id", "?"),
        "statement": _pending(h.get("statement") or None),
        "result": _pending(result_val),
        "effect_size": _pending(None),
        "item_type": "hypothesis",
    }


def _build_study(old: dict) -> dict:
    rd = old.get("research_design") or {}
    sample = old.get("sample") or {}
    constructs_old = old.get("constructs") or {}
    hypotheses_old = old.get("hypotheses") or []

    all_constructs = []
    for c in constructs_old.get("independent_variables", []):
        m = _migrate_construct(c)
        m["role"] = "independent"
        all_constructs.append(m)
    for c in constructs_old.get("dependent_variables", []):
        m = _migrate_construct(c)
        m["role"] = "dependent"
        all_constructs.append(m)
    for c in constructs_old.get("mediators", []):
        m = _migrate_construct(c)
        m["role"] = "mediator"
        all_constructs.append(m)
    for c in constructs_old.get("moderators", []):
        m = _migrate_construct(c)
        m["role"] = "moderator"
        all_constructs.append(m)

    return {
        "study_id": "single",
        "design": {
            "methodology":     _pending(rd.get("methodology")),
            "study_type":      _pending(rd.get("study_type")),
            "data_collection": _pending(rd.get("data_collection")),
            "country":         _pending(sample.get("country")),
        },
        "sample": {
            "total_n":               _pending(sample.get("total_n")),
            "population":            _pending(sample.get("population") or None),
            "age_mean":              _pending(sample.get("age_mean")),
            "age_range":             _pending(sample.get("age_range")),
            "gender_percent_female": _pending(sample.get("gender_percent_female")),
        },
        "constructs":    all_constructs,
        "hypotheses":    [_migrate_hypothesis(h) for h in hypotheses_old],
        "results_notes": None,
    }


def _migrate_key_findings(old_findings: list) -> list:
    result = []
    for f in old_findings:
        if isinstance(f, str):
            result.append({
                "statement": f,
                "finding_type": "main_result",
                "quote": None,
                "page": None,
                "section": None,
            })
        elif isinstance(f, dict):
            result.append(f)
    return result


def migrate_one(old: dict) -> dict:
    old_type = (old.get("metadata") or {}).get("paper_type", "")
    paper_type = _map_paper_type(old_type)
    meta = old.get("metadata") or {}

    new = {
        "paper_id": old.get("paper_id", ""),
        "schema_version": SCHEMA_VERSION,
        "annotation_provenance": _infer_provenance(old),
        "metadata": {
            "title":       _pending(meta.get("title") or None),
            "authors":     _pending(meta.get("authors") or None),
            "year":        _pending(meta.get("year")),
            "journal":     _pending(meta.get("journal") or None),
            "doi":         _pending(meta.get("doi")),
            "paper_type_profile": paper_type,
            "publication_version": _infer_pub_version(old),
        },
        "studies": [],
        "key_findings": _migrate_key_findings(old.get("key_findings") or []),
        "theoretical_framework": old.get("theoretical_framework") or [],
        "notes": old.get("notes") or "",
    }

    # Only add studies if the old schema had any research design / constructs
    rd = old.get("research_design") or {}
    has_design = any(rd.get(k) for k in ("methodology", "study_type", "data_collection"))
    has_sample = any((old.get("sample") or {}).get(k) for k in ("total_n", "population"))
    has_constructs = any(
        (old.get("constructs") or {}).get(k)
        for k in ("independent_variables", "dependent_variables", "mediators", "moderators")
    )

    if has_design or has_sample or has_constructs or old.get("hypotheses"):
        new["studies"] = [_build_study(old)]

    return new


def is_v1(data: dict) -> bool:
    return data.get("schema_version") != SCHEMA_VERSION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(ANN_DIR))
    parser.add_argument("--write", action="store_true", help="Write migrated files (default: dry run)")
    parser.add_argument("--backup", action="store_true", help="Keep original as .v1.bak")
    args = parser.parse_args()

    ann_dir = Path(args.dir)
    files = sorted(ann_dir.glob("*.json"))
    NON_ANNOTATION = {"schema.json", "pilot_manifest.json"}
    files = [f for f in files if f.name not in NON_ANNOTATION]

    needs_migration = [f for f in files if is_v1(json.loads(f.read_text(encoding="utf-8")))]

    if not needs_migration:
        print("All annotation files are already at schema v2.0.")
        return

    print(f"{'DRY RUN — ' if not args.write else ''}Migrating {len(needs_migration)} file(s):\n")

    for f in needs_migration:
        old = json.loads(f.read_text(encoding="utf-8"))
        new = migrate_one(old)
        print(f"  {f.name}")
        print(f"    origin={new['annotation_provenance']['origin']}  "
              f"review={new['annotation_provenance']['review_status']}")
        print(f"    paper_type: {old.get('metadata',{}).get('paper_type','?')} → {new['metadata']['paper_type_profile']}")
        print(f"    studies: {len(new['studies'])}  findings: {len(new['key_findings'])}")

        if args.write:
            if args.backup:
                shutil.copy2(f, f.with_suffix(".v1.bak"))
            f.write_text(json.dumps(new, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"    → written")

    if not args.write:
        print("\nDry run complete. Add --write to apply changes.")
    else:
        print(f"\nMigration complete. Run: python tools/validate_annotations.py")


if __name__ == "__main__":
    main()
