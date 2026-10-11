#!/usr/bin/env python3
"""Generate per-paper annotation template JSON files (schema v2.0).

Usage:
    python tools/create_annotation_templates.py
    python tools/create_annotation_templates.py --pdf-dir data/papers/pilot_10 --out-dir data/annotations
"""

import argparse
import json
import re
from pathlib import Path

SCHEMA_VERSION = "2.1"


def _pending(value=None) -> dict:
    return {"value": value, "status": "pending", "quote": None, "page": None, "section": None, "fragment_id": None}


def make_template(pdf_path: Path) -> dict:
    stem = pdf_path.stem
    parts = [p.strip() for p in stem.split(" - ", 2)]
    year = None
    if len(parts) >= 2:
        try:
            year = int(parts[1])
        except ValueError:
            pass

    return {
        "paper_id": stem[:80],
        "schema_version": SCHEMA_VERSION,

        "annotation_provenance": {
            "origin": "human",
            "review_status": "unreviewed",
            "created_by": "",
            "created_date": "",
            "model_id": None,
            "reviewed_by": None,
            "reviewed_date": None,
            "human_read_time_minutes": None,
            "model_run_time_seconds": None,
            "correction_time_minutes": None,
        },

        "metadata": {
            "title":       _pending(),
            "authors":     _pending(),
            "year":        _pending(year),
            "journal":     _pending(),
            "doi":         _pending(),
            "paper_type_profile": "quantitative_empirical",
            "publication_version": "unknown",
        },

        "studies": [
            {
                "study_id": "single",
                "design": {
                    "methodology":     _pending(),
                    "study_type":      _pending(),
                    "data_collection": _pending(),
                    "country":         _pending(),
                },
                "sample": {
                    "total_n":               _pending(),
                    "population":            _pending(),
                    "age_mean":              _pending(),
                    "age_range":             _pending(),
                    "gender_percent_female": _pending(),
                },
                "constructs": [],
                "hypotheses": [],
                "results_notes": None,
            }
        ],

        "key_findings": [],
        "theoretical_framework": [],
        "notes": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", default="data/papers/pilot_10")
    parser.add_argument("--out-dir", default="data/annotations")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {pdf_dir}")
        return

    created = skipped = 0
    for pdf in pdfs:
        safe_name = re.sub(r'[<>:"/\\|?*]', '', pdf.stem)[:80]
        out_file = out_dir / f"{safe_name}.json"
        if out_file.exists():
            print(f"SKIP (exists): {out_file.name}")
            skipped += 1
            continue
        t = make_template(pdf)
        out_file.write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Created: {out_file.name}")
        created += 1

    print(f"\nDone: {created} created, {skipped} skipped")
    print(f"Annotation files in: {out_dir}/")
    print(f"Fill in annotation_provenance.created_by and annotation_date before annotating.")


if __name__ == "__main__":
    main()
