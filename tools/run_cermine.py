"""
Run CERMINE on a PDF via the public REST API and save structured results.

Usage:
    python tools/run_cermine.py <path_to_pdf>
    python tools/run_cermine.py <path_to_pdf> --out data/output/agent1_cermine_result.json
"""

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

CERMINE_URL = "http://cermine.ceon.pl/extract.do"


# ─────────────────────────────────────────── API call ────────────────────────

def call_cermine(pdf_path: Path, timeout: int = 600) -> str:
    print(f"  Sending to CERMINE API ({pdf_path.name}, {pdf_path.stat().st_size // 1024} KB)...")
    print(f"  This may take 2–4 minutes for a 26-page PDF...")
    t0 = time.perf_counter()

    with open(pdf_path, "rb") as f:
        response = requests.post(
            CERMINE_URL,
            data=f.read(),
            headers={"Content-Type": "application/binary"},
            timeout=timeout,
        )

    elapsed = time.perf_counter() - t0
    print(f"  Response: HTTP {response.status_code} | {len(response.content)} bytes | {elapsed:.1f}s")

    if response.status_code != 200:
        raise RuntimeError(f"CERMINE returned HTTP {response.status_code}: {response.text[:200]}")

    return response.text


# ─────────────────────────────────────────── XML parser ──────────────────────

def parse_cermine_xml(xml_text: str) -> dict:
    # Fix encoding issues (CERMINE sometimes emits non-UTF-8 bytes)
    fixed = xml_text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    # Also clean up any remaining replacement chars in tag text
    root = ET.fromstring(fixed)

    def text(el) -> str:
        if el is None:
            return ""
        return "".join(el.itertext()).strip()

    def find(path):
        return root.find(path)

    def findall(path):
        return root.findall(path)

    # ── Title ──────────────────────────────────────────────────────────────
    title = text(find(".//article-meta/title-group/article-title"))

    # ── Authors ────────────────────────────────────────────────────────────
    authors = []
    for contrib in findall(".//article-meta/contrib-group/contrib[@contrib-type='author']"):
        name_el = contrib.find("string-name")
        if name_el is not None:
            authors.append(text(name_el))
        else:
            gn = text(contrib.find("given-names"))
            sn = text(contrib.find("surname"))
            if gn or sn:
                authors.append(f"{gn} {sn}".strip())

    # ── DOI ───────────────────────────────────────────────────────────────
    doi_el = find(".//article-meta/article-id[@pub-id-type='doi']")
    doi = text(doi_el) if doi_el is not None else ""

    # ── Dates ─────────────────────────────────────────────────────────────
    date_received = date_accepted = ""
    for date_el in findall(".//article-meta/history/date"):
        dtype = date_el.get("date-type", "")
        day   = text(date_el.find("day"))
        month = text(date_el.find("month"))
        year  = text(date_el.find("year"))
        date_str = f"{day} {month} {year}".strip()
        if dtype == "received":
            date_received = date_str
        elif dtype == "accepted":
            date_accepted = date_str

    # ── Abstract ──────────────────────────────────────────────────────────
    abstract_el = find(".//article-meta/abstract")
    abstract = text(abstract_el) if abstract_el is not None else ""

    # ── Keywords ──────────────────────────────────────────────────────────
    kwd_group = find(".//article-meta/kwd-group")
    keywords = []
    if kwd_group is not None:
        keywords = [text(k) for k in kwd_group.findall("kwd") if text(k)]

    # ── Journal ───────────────────────────────────────────────────────────
    journal = text(find(".//journal-meta/journal-title-group/journal-title"))

    # ── Sections ──────────────────────────────────────────────────────────
    sections = []
    for sec in findall(".//body//sec"):
        title_el = sec.find("title")
        if title_el is not None:
            sec_title = text(title_el)
            if sec_title:
                sections.append(sec_title)

    # ── Full body text ─────────────────────────────────────────────────────
    body_el = find(".//body")
    body_text = text(body_el) if body_el is not None else ""

    # ── References ────────────────────────────────────────────────────────
    references = []
    for ref in findall(".//back//ref"):
        ref_id = ref.get("id", "")
        cite_el = ref.find("mixed-citation")
        if cite_el is not None:
            ref_text = text(cite_el)
        else:
            ref_text = text(ref)
        if ref_text:
            references.append(ref_text)

    # ── Build full text ───────────────────────────────────────────────────
    full_text = "\n\n".join(filter(None, [abstract, body_text]))
    words = len(full_text.split())

    return {
        "parser": "cermine",
        "title": title,
        "authors": authors,
        "doi": doi,
        "journal": journal,
        "date_received": date_received,
        "date_accepted": date_accepted,
        "abstract": abstract,
        "keywords": keywords,
        "sections": sections,
        "references": references,
        "text": full_text,
        "word_count": words,
        "section_count": len(sections),
        "reference_count": len(references),
    }


# ─────────────────────────────────────────── main ────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Run CERMINE on a PDF and save JSON results")
    ap.add_argument("pdf", help="Path to PDF file")
    ap.add_argument("--out", default="", help="Output JSON path")
    ap.add_argument("--xml-out", default="", help="Also save raw CERMINE XML")
    ap.add_argument("--cached", default="", help="Use cached XML file instead of calling API")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}")
        sys.exit(1)

    out_path = Path(args.out) if args.out else \
        Path("data/output") / f"agent1_cermine_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Get XML
    if args.cached and Path(args.cached).exists():
        print(f"  Using cached XML: {args.cached}")
        xml_text = Path(args.cached).read_text(encoding="utf-8", errors="replace")
    else:
        xml_text = call_cermine(pdf_path)
        if args.xml_out:
            Path(args.xml_out).write_text(xml_text, encoding="utf-8")
            print(f"  XML saved → {args.xml_out}")

    print("  Parsing CERMINE XML...")
    result = parse_cermine_xml(xml_text)

    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  JSON saved → {out_path}")

    # Console summary
    print(f"\n┌─ CERMINE results ───────────────────────────────────────────┐")
    print(f"│ Title     : {result['title'][:60]}")
    print(f"│ Authors   : {', '.join(result['authors'][:4])}")
    print(f"│ DOI       : {result['doi']}")
    print(f"│ Received  : {result['date_received']}")
    print(f"│ Accepted  : {result['date_accepted']}")
    print(f"│ Keywords  : {', '.join(result['keywords'][:5]) or '—'}")
    print(f"│ Sections  : {result['section_count']}")
    print(f"│ References: {result['reference_count']}")
    print(f"│ Words     : {result['word_count']:,}")
    print(f"└─────────────────────────────────────────────────────────────┘")


if __name__ == "__main__":
    main()
