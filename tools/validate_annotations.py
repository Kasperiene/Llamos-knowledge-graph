#!/usr/bin/env python3
"""Check annotation completeness and print a progress table.

Usage:
    python tools/validate_annotations.py
    python tools/validate_annotations.py --dir data/annotations
"""

import argparse
import json
from pathlib import Path

REQUIRED_FIELDS = [
    ("metadata.title",        lambda d: bool(d["metadata"]["title"])),
    ("metadata.authors",      lambda d: len(d["metadata"]["authors"]) > 0),
    ("metadata.year",         lambda d: d["metadata"]["year"] is not None),
    ("metadata.journal",      lambda d: bool(d["metadata"]["journal"])),
    ("metadata.paper_type",   lambda d: d["metadata"]["paper_type"] in
                                        ("empirical", "theoretical", "review", "mixed")),
    ("research_design.methodology", lambda d: d["research_design"]["methodology"] is not None
                                              or d["metadata"]["paper_type"] in ("theoretical", "review")),
    ("sample.total_n",        lambda d: d["sample"]["total_n"] is not None
                                        or d["metadata"]["paper_type"] in ("theoretical", "review")),
    ("sample.population",     lambda d: bool(d["sample"]["population"])
                                        or d["metadata"]["paper_type"] in ("theoretical", "review")),
    ("constructs.iv",         lambda d: len(d["constructs"]["independent_variables"]) > 0
                                        or d["metadata"]["paper_type"] in ("theoretical", "review")),
    ("constructs.dv",         lambda d: len(d["constructs"]["dependent_variables"]) > 0
                                        or d["metadata"]["paper_type"] in ("theoretical", "review")),
    ("key_findings",          lambda d: len(d["key_findings"]) > 0),
    ("theoretical_framework", lambda d: len(d["theoretical_framework"]) > 0),
    ("annotator",             lambda d: bool(d["annotator"])),
    ("annotation_date",       lambda d: bool(d["annotation_date"])),
]


def check(data: dict) -> dict:
    results = {}
    for name, fn in REQUIRED_FIELDS:
        try:
            results[name] = fn(data)
        except Exception:
            results[name] = False
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="data/annotations")
    args = parser.parse_args()

    ann_dir = Path(args.dir)
    files = sorted(ann_dir.glob("*.json"))
    files = [f for f in files if f.name != "schema.json"]

    if not files:
        print(f"No annotation files found in {ann_dir}")
        return

    all_results = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        checks = check(data)
        score = sum(checks.values())
        total = len(checks)
        all_results.append({
            "file": f.name[:55],
            "score": score,
            "total": total,
            "pct": score / total * 100,
            "checks": checks,
            "annotator": data.get("annotator", ""),
            "time_min": data.get("annotation_time_minutes"),
        })

    print(f"\n{'FILE':<56} {'SCORE':>7}  {'ANNOTATOR':<20}  {'TIME(min)'}")
    print("─" * 100)
    for r in all_results:
        bar = "█" * r["score"] + "░" * (r["total"] - r["score"])
        print(f"{r['file']:<56} {r['score']:>2}/{r['total']}  {r['annotator']:<20}  {r['time_min'] or '—'}")

    done = sum(1 for r in all_results if r["pct"] == 100)
    print(f"\nCompleted: {done}/{len(all_results)} papers fully annotated")

    # Detail on failed checks
    incomplete = [r for r in all_results if r["pct"] < 100]
    if incomplete:
        print("\nMissing fields:")
        for r in incomplete:
            missing = [k for k, v in r["checks"].items() if not v]
            print(f"  {r['file'][:50]}: {', '.join(missing)}")


if __name__ == "__main__":
    main()
