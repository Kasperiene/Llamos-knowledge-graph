#!/usr/bin/env python3
"""Download open-access PDFs from the 2025 Identity Leadership SLR reference list.

Source: Lê Hoang et al. (2025) - Identity leadership: a systematic literature review
DOI: 10.1007/s11301-025-00554-0

Usage:
    python tools/download_slr_papers.py
    python tools/download_slr_papers.py --out-dir data/papers/slr_corpus
"""

import argparse
import json
import re
import time
from pathlib import Path

import requests

REFERENCES_JSON = Path(__file__).parent.parent / "data/papers/slr_oa_references.json"
DEFAULT_OUT = Path(__file__).parent.parent / "data/papers/slr_corpus"
HEADERS = {"User-Agent": "Mozilla/5.0 (research pipeline; mailto:research@pipeline.local)"}


def safe_filename(title: str, author: str, year: int) -> str:
    name = f"{author} - {year} - {title}"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:120] + ".pdf"


def already_downloaded(out_dir: Path, filename: str) -> bool:
    return (out_dir / filename).exists()


def download_pdf(url: str, dest: Path, timeout: int = 30) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        if r.status_code != 200:
            return False
        content_type = r.headers.get("content-type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            first_bytes = b""
            for chunk in r.iter_content(1024):
                first_bytes = chunk
                break
            if not first_bytes.startswith(b"%PDF"):
                return False
            dest.write_bytes(first_bytes + b"".join(r.iter_content(8192)))
            return True
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"    [!] Download error: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    papers = json.loads(REFERENCES_JSON.read_text(encoding="utf-8"))
    print(f"Loaded {len(papers)} open-access papers from reference list")

    existing = list(out_dir.glob("*.pdf"))
    print(f"Already in {out_dir.name}/: {len(existing)} PDFs\n")

    ok = skipped = failed = 0

    for i, paper in enumerate(papers, 1):
        filename = safe_filename(paper["title"], paper["first_author"], paper["year"])
        dest = out_dir / filename

        if dest.exists():
            print(f"[{i:02d}/{len(papers)}] SKIP (exists): {filename[:70]}")
            skipped += 1
            continue

        print(f"[{i:02d}/{len(papers)}] Downloading: {filename[:70]}")
        success = download_pdf(paper["pdf_url"], dest)
        if success:
            size_kb = dest.stat().st_size // 1024
            print(f"         OK ({size_kb} KB)")
            ok += 1
        else:
            print(f"         FAILED: {paper['pdf_url'][:80]}")
            failed += 1

        time.sleep(args.delay)

    print(f"\nDone: {ok} downloaded, {skipped} skipped, {failed} failed")
    total = len(list(out_dir.glob("*.pdf")))
    print(f"Total PDFs in {out_dir.name}/: {total}")


if __name__ == "__main__":
    main()
