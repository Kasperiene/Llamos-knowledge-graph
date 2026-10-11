#!/usr/bin/env python3
"""Generate per-paper annotation template JSON files from pilot_10 folder.

Usage:
    python tools/create_annotation_templates.py
    python tools/create_annotation_templates.py --pdf-dir data/papers/pilot_10 --out-dir data/annotations
"""

import argparse
import json
import re
from pathlib import Path

TEMPLATE = {
    "paper_id": None,
    "annotator": "",
    "annotation_date": "",
    "annotation_time_minutes": None,

    "metadata": {
        "title": "",
        "authors": [],
        "year": None,
        "journal": "",
        "doi": None,
        "paper_type": ""
    },

    "research_design": {
        "methodology": None,
        "study_type": None,
        "number_of_studies": 1,
        "data_collection": None
    },

    "sample": {
        "total_n": None,
        "population": "",
        "country": None,
        "age_mean": None,
        "age_range": None,
        "gender_percent_female": None
    },

    "constructs": {
        "independent_variables": [],
        "dependent_variables": [],
        "mediators": [],
        "moderators": []
    },

    "hypotheses": [],

    "key_findings": [],

    "theoretical_framework": [],

    "notes": ""
}


def parse_filename(stem: str) -> dict:
    """Extract author/year hint from filename like 'LastName - YYYY - Title...'"""
    parts = [p.strip() for p in stem.split(" - ", 2)]
    year = None
    if len(parts) >= 2:
        try:
            year = int(parts[1])
        except ValueError:
            pass
    return {"year_hint": year}


def make_template(pdf_path: Path) -> dict:
    stem = pdf_path.stem
    hint = parse_filename(stem)
    t = json.loads(json.dumps(TEMPLATE))
    t["paper_id"] = stem[:80]
    if hint["year_hint"]:
        t["metadata"]["year"] = hint["year_hint"]
    return t


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


if __name__ == "__main__":
    main()
