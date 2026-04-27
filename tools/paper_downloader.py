"""
Paper Downloader
Searches Semantic Scholar + OpenAlex for open-access papers and downloads PDFs.
Usage: python tools/paper_downloader.py "query" output_folder
"""

import sys
import time
import requests
from pathlib import Path


def search_semantic_scholar(query: str, limit: int = 100) -> list:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "paperId,title,year,openAccessPdf,authors,abstract",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        papers = []
        for p in data.get("data", []):
            pdf = p.get("openAccessPdf")
            if pdf and pdf.get("url"):
                papers.append({
                    "source": "SemanticScholar",
                    "title": p.get("title", "untitled"),
                    "year": p.get("year"),
                    "pdf_url": pdf["url"],
                })
        return papers
    except Exception as e:
        print(f"  [!] Semantic Scholar error: {e}")
        return []


def search_openalex(query: str, limit: int = 100) -> list:
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "filter": "open_access.is_oa:true,has_doi:true",
        "per-page": limit,
        "select": "title,publication_year,open_access,doi",
        "mailto": "research@pipeline.local",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        papers = []
        for p in r.json().get("results", []):
            oa = p.get("open_access", {})
            pdf_url = oa.get("oa_url")
            if pdf_url and pdf_url.endswith(".pdf"):
                papers.append({
                    "source": "OpenAlex",
                    "title": p.get("title", "untitled"),
                    "year": p.get("publication_year"),
                    "pdf_url": pdf_url,
                })
        return papers
    except Exception as e:
        print(f"  [!] OpenAlex error: {e}")
        return []


def deduplicate(papers: list) -> list:
    seen = set()
    unique = []
    for p in papers:
        key = p["pdf_url"]
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def safe_filename(title: str, year, index: int) -> str:
    clean = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
    clean = clean.strip()[:80]
    return f"{index:03d}_{year}_{clean}.pdf"


def download_papers(papers: list, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded, failed = 0, 0

    for i, paper in enumerate(papers, 1):
        filename = safe_filename(paper["title"], paper["year"], i)
        dest = output_dir / filename

        if dest.exists():
            print(f"  [skip] {filename}")
            continue

        try:
            r = requests.get(paper["pdf_url"], timeout=30, stream=True)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            if "pdf" not in content_type and not paper["pdf_url"].endswith(".pdf"):
                print(f"  [skip] Not a PDF: {paper['title'][:60]}")
                failed += 1
                continue

            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_kb = dest.stat().st_size // 1024
            print(f"  [{i:03d}] Downloaded ({size_kb} KB): {paper['title'][:60]}")
            downloaded += 1
            time.sleep(0.5)

        except Exception as e:
            print(f"  [fail] {paper['title'][:60]} — {e}")
            failed += 1

    return downloaded, failed


def run(query: str, output_dir: Path):
    print(f"\nQuery: \"{query}\"")
    print("Searching Semantic Scholar...")
    ss_papers = search_semantic_scholar(query)

    print("Searching OpenAlex...")
    oa_papers = search_openalex(query)

    all_papers = deduplicate(ss_papers + oa_papers)

    print(f"\n{'='*50}")
    print(f"  Found {len(ss_papers)} papers on Semantic Scholar (with free PDF)")
    print(f"  Found {len(oa_papers)} papers on OpenAlex (with free PDF)")
    print(f"  Total unique papers with downloadable PDF: {len(all_papers)}")
    print(f"{'='*50}")

    if not all_papers:
        print("No downloadable papers found.")
        return

    confirm = input(f"\nDownload {len(all_papers)} papers to '{output_dir}'? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    print(f"\nDownloading to {output_dir}...\n")
    downloaded, failed = download_papers(all_papers, output_dir)

    print(f"\n{'='*50}")
    print(f"  Downloaded: {downloaded}")
    print(f"  Failed:     {failed}")
    print(f"  Folder:     {output_dir}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Russian cyber groups Telegram"
    folder = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/papers/russian_cyber_telegram")
    run(query, folder)
