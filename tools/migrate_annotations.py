#!/usr/bin/env python3
"""Migrate annotation files: v1 → v2.0 → v2.1.

v1→v2.0: flat fields → Claim objects, all status=pending.
v2.0→v2.1: add status to key_findings; convert theoretical_framework to objects;
           fix time fields; normalize paper_id; fix unknown origin.

Usage:
    python tools/migrate_annotations.py               # dry run
    python tools/migrate_annotations.py --write       # write files
    python tools/migrate_annotations.py --write --backup
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ANN_DIR = Path(__file__).parent.parent / "data/annotations"
NON_ANNOTATION = {"schema.json", "pilot_manifest.json"}
MODEL_NAME_RE = re.compile(r"claude|openai|gpt|gemini|llama|mistral|model", re.IGNORECASE)
SMART_QUOTES = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"'})


def normalize_paper_id(stem: str) -> str:
    return stem.translate(SMART_QUOTES)[:80]


def _pending(value=None) -> dict:
    return {"value": value, "status": "pending", "quote": None, "page": None,
            "section": None, "fragment_id": None}


# ── v1 → v2.0 ──────────────────────────────────────────────────────────────

def _infer_origin_v1(annotator: str) -> str:
    if not annotator or not annotator.strip():
        return "unknown"
    if MODEL_NAME_RE.search(annotator):
        return "model"
    return "human"


def _map_paper_type(old_type: str) -> str:
    return {
        "empirical": "quantitative_empirical",
        "theoretical": "theoretical",
        "review": "review",
        "mixed": "mixed_methods",
        "qualitative": "qualitative_empirical",
        "scale_validation": "scale_validation",
    }.get((old_type or "").lower(), "other")


def _migrate_construct_v1(c: dict, role: str) -> dict:
    alpha = c.get("reliability_alpha")
    return {
        "name":             _pending(c.get("name") or None),
        "role":             role,
        "measure_name":     _pending(c.get("measure") or None),
        "items_n":          _pending(c.get("items") or None),
        "reliability":      _pending(alpha),
        "reliability_type": "alpha" if alpha is not None else None,
        "psychometric_notes": None,
    }


def _migrate_hypothesis_v1(h: dict) -> dict:
    supported = h.get("supported")
    result_val = {True: "supported", False: "not supported"}.get(supported)
    return {
        "id":          h.get("id", "?"),
        "statement":   _pending(h.get("statement") or None),
        "result":      _pending(result_val),
        "effect_size": _pending(None),
        "item_type":   "hypothesis",
    }


def _build_study_v1(old: dict) -> dict:
    rd = old.get("research_design") or {}
    sample = old.get("sample") or {}
    constructs = old.get("constructs") or {}
    role_map = {"independent_variables": "independent", "dependent_variables": "dependent",
                "mediators": "mediator", "moderators": "moderator"}
    all_constructs = [
        _migrate_construct_v1(c, role)
        for key, role in role_map.items()
        for c in constructs.get(key, [])
    ]
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
        "hypotheses":    [_migrate_hypothesis_v1(h) for h in old.get("hypotheses") or []],
        "results_notes": None,
    }


def migrate_v1_to_v20(old: dict) -> dict:
    annotator = old.get("annotator", "")
    origin = _infer_origin_v1(annotator)
    old_time = old.get("annotation_time_minutes")
    meta = old.get("metadata") or {}

    new = {
        "paper_id": normalize_paper_id(old.get("paper_id", "")),
        "schema_version": "2.0",
        "annotation_provenance": {
            "origin":      origin,
            "review_status": "unreviewed",
            "created_by":  annotator or "unknown",
            "created_date": old.get("annotation_date") or "",
            "model_id":    annotator if origin == "model" else None,
            "reviewed_by": None, "reviewed_date": None,
            "human_read_time_minutes":  old_time if origin == "human" else None,
            "model_run_time_seconds":   None,
            "correction_time_minutes":  None,
            "legacy_time_minutes":      old_time if origin not in ("human",) else None,
        },
        "metadata": {
            "title":   _pending(meta.get("title") or None),
            "authors": _pending(meta.get("authors") or None),
            "year":    _pending(meta.get("year")),
            "journal": _pending(meta.get("journal") or None),
            "doi":     _pending(meta.get("doi")),
            "paper_type_profile":  _map_paper_type(meta.get("paper_type", "")),
            "publication_version": "unknown",
        },
        "studies": [],
        "key_findings": [],
        "theoretical_framework": [],
        "notes": old.get("notes") or "",
    }

    # studies
    rd = old.get("research_design") or {}
    sample = old.get("sample") or {}
    constructs = old.get("constructs") or {}
    has_content = (
        any(rd.get(k) for k in ("methodology", "study_type", "data_collection")) or
        any(sample.get(k) for k in ("total_n", "population")) or
        any(constructs.get(k) for k in ("independent_variables", "dependent_variables")) or
        old.get("hypotheses")
    )
    if has_content:
        new["studies"] = [_build_study_v1(old)]

    # key_findings (v1 has plain strings)
    for f in old.get("key_findings") or []:
        if isinstance(f, str):
            new["key_findings"].append({"statement": f, "status": "pending",
                                        "finding_type": None, "quote": None, "page": None, "section": None})

    # theoretical_framework (v1 has strings)
    for tf in old.get("theoretical_framework") or []:
        new["theoretical_framework"].append({"name": tf, "status": "pending",
                                             "quote": None, "page": None, "section": None})
    return new


# ── v2.0 → v2.1 ────────────────────────────────────────────────────────────

def migrate_v20_to_v21(old: dict) -> dict:
    new = json.loads(json.dumps(old))  # deep copy
    new["schema_version"] = "2.1"

    # Normalize paper_id
    new["paper_id"] = normalize_paper_id(new.get("paper_id", ""))

    # Fix annotation_provenance
    prov = new["annotation_provenance"]

    # origin: empty created_by → unknown
    if not prov.get("created_by") or prov["created_by"] == "unknown":
        if prov["origin"] == "human":
            prov["origin"] = "unknown"

    # Fix time fields: model_run_time_seconds must NOT be minutes converted from legacy
    # If model_run_time_seconds is set and legacy_time_minutes is null, it was likely a bad conversion
    if "legacy_time_minutes" not in prov:
        prov["legacy_time_minutes"] = None

    if prov.get("model_run_time_seconds") is not None and prov.get("legacy_time_minutes") is None:
        # Value came from old annotation_time_minutes → move to legacy
        prov["legacy_time_minutes"] = prov["model_run_time_seconds"]
        prov["model_run_time_seconds"] = None

    # key_findings: add status if missing
    for item in new.get("key_findings", []):
        if "status" not in item:
            item["status"] = "pending"

    # theoretical_framework: convert strings to TheoreticalRef objects
    new_tf = []
    for item in new.get("theoretical_framework", []):
        if isinstance(item, str):
            new_tf.append({"name": item, "status": "pending",
                           "quote": None, "page": None, "section": None})
        elif isinstance(item, dict):
            if "status" not in item:
                item["status"] = "pending"
            new_tf.append(item)
    new["theoretical_framework"] = new_tf

    return new


# ── dispatch ────────────────────────────────────────────────────────────────

def needs_migration(data: dict) -> bool:
    return data.get("schema_version") != "2.1"


def migrate_one(data: dict) -> dict:
    ver = data.get("schema_version")
    if ver is None:
        data = migrate_v1_to_v20(data)
    if data.get("schema_version") == "2.0":
        data = migrate_v20_to_v21(data)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(ANN_DIR))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()

    ann_dir = Path(args.dir)
    files = [f for f in sorted(ann_dir.glob("*.json")) if f.name not in NON_ANNOTATION]
    to_migrate = [f for f in files if needs_migration(json.loads(f.read_text(encoding="utf-8")))]

    if not to_migrate:
        print("All annotation files are at schema v2.1.")
        return

    prefix = "DRY RUN — " if not args.write else ""
    print(f"{prefix}Migrating {len(to_migrate)} file(s):\n")

    for f in to_migrate:
        old = json.loads(f.read_text(encoding="utf-8"))
        new = migrate_one(old)
        prov = new["annotation_provenance"]
        print(f"  {f.name}")
        print(f"    {old.get('schema_version','v1')} → {new['schema_version']}")
        print(f"    origin={prov['origin']}  review={prov['review_status']}")
        print(f"    paper_id normalized: {repr(old.get('paper_id','')[:50])} → {repr(new['paper_id'][:50])}")
        if args.write:
            if args.backup:
                shutil.copy2(f, f.with_suffix(f".{old.get('schema_version','v1').replace('.','')}.bak"))
            f.write_text(json.dumps(new, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"    → written")

    if not args.write:
        print("\nDry run. Add --write to apply.")
    else:
        print("\nDone. Run: python tools/validate_annotations.py")


if __name__ == "__main__":
    main()
