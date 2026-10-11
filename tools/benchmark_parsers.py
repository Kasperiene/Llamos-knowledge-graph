"""
Parser benchmark tool for Agent 1 — Data Ingestion.

Tests multiple PDF/document parsing backends on the same file and exports
a side-by-side comparison to Excel.

Usage:
    python tools/benchmark_parsers.py <path_to_pdf>
    python tools/benchmark_parsers.py <path_to_pdf> --ocr      # include OCR engines (slow)
    python tools/benchmark_parsers.py <path_to_pdf> --out results/my_report.xlsx
"""

import re
import sys
import time
import argparse
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

# Excel rejects control characters outside the allowed XML 1.0 range
_ILLEGAL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

def _sanitize(value):
    """Strip characters that openpyxl / Excel cannot store in a cell."""
    if isinstance(value, str):
        return _ILLEGAL_CHARS.sub("", value)
    return value


# ─────────────────────────────────────────── text utilities ──────────────────

def clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"-\n(\w)", r"\1", text)
    return text.strip()


def is_section_header(line: str) -> bool:
    if len(line) > 80:
        return False
    if re.match(r"^\d+[\.\)]\s+\w", line):
        return True
    if line.isupper() and 3 < len(line) < 60:
        return True
    if re.match(r"^(Abstract|Introduction|Conclusion|Related Work|Method|Background|Discussion|Results|Experiment)", line, re.I):
        return True
    return False


def extract_structure(text: str) -> tuple:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = lines[0] if lines else ""
    sections, references = [], []
    in_refs = False
    for line in lines[1:]:
        low = line.lower()
        if low in ("references", "bibliography", "works cited"):
            in_refs = True
            continue
        if in_refs:
            references.append(line)
        elif is_section_header(line):
            sections.append(line)
    return title, sections, references


# ─────────────────────────────────────────── parsers ─────────────────────────

def _pymupdf_simple(path: Path) -> str:
    import fitz
    doc = fitz.open(str(path))
    return "\n".join(page.get_text() for page in doc)


def _pymupdf_blocks(path: Path) -> str:
    """Layout-aware: sorts text blocks by vertical then horizontal position."""
    import fitz
    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))
        pages.append("\n".join(b[4].strip() for b in blocks if b[4].strip()))
    return "\n".join(pages)


def _pymupdf_dict(path: Path) -> str:
    """Span-level extraction — preserves reading order of spans."""
    import fitz
    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        spans = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    spans.append(span["text"])
        pages.append(" ".join(spans))
    return "\n".join(pages)


def _pdfplumber(path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _pdfminer(path: Path) -> str:
    from pdfminer.high_level import extract_text
    return extract_text(str(path))


def _pypdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _ocr_tesseract(path: Path) -> str:
    import pytesseract
    from pdf2image import convert_from_path
    images = convert_from_path(str(path), dpi=300)
    return "\n".join(pytesseract.image_to_string(img) for img in images)


def _ocr_easyocr(path: Path) -> str:
    import easyocr
    import numpy as np
    from pdf2image import convert_from_path
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    images = convert_from_path(str(path), dpi=200)
    pages = []
    for img in images:
        results = reader.readtext(np.array(img), detail=0, paragraph=True)
        pages.append("\n".join(results))
    return "\n".join(pages)


# ─────────────────────────────────────────── runner ──────────────────────────

PARSERS = [
    ("PyMuPDF — simple",   _pymupdf_simple,  "Text layer; fastest, widely used"),
    ("PyMuPDF — blocks",   _pymupdf_blocks,  "Text layer; layout-sorted blocks"),
    ("PyMuPDF — dict",     _pymupdf_dict,    "Text layer; span-level, preserves order"),
    ("pdfplumber",         _pdfplumber,      "Text layer; good for tables/columns"),
    ("pdfminer.six",       _pdfminer,        "Text layer; low-level, high fidelity"),
    ("pypdf",              _pypdf,           "Text layer; lightweight pure-Python"),
]

OCR_PARSERS = [
    ("OCR — Tesseract",  _ocr_tesseract, "OCR; classical, CPU-based"),
    ("OCR — EasyOCR",    _ocr_easyocr,   "OCR; deep-learning, CPU mode"),
]


def run_one(name: str, fn, path: Path) -> dict:
    print(f"  Running {name}...", end="", flush=True)
    try:
        t0 = time.perf_counter()
        raw = fn(path)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        text = clean_text(raw)
        title, sections, references = extract_structure(text)
        print(f" {elapsed_ms:.0f} ms  |  {len(text):,} chars")
        return {
            "Parser": name,
            "Status": "OK",
            "Time (ms)": round(elapsed_ms, 1),
            "Chars": len(text),
            "Words": len(text.split()),
            "Lines": text.count("\n"),
            "Sections found": len(sections),
            "References found": len(references),
            "Title detected": title[:100],
            "Section headers (first 5)": " | ".join(sections[:5]),
            "Text sample (first 400 chars)": text[:400].replace("\n", " ↵ "),
            "Error": "",
            "_full_text": text,
        }
    except Exception as exc:
        print(f" ERROR: {exc}")
        return {
            "Parser": name,
            "Status": "ERROR",
            "Time (ms)": 0,
            "Chars": 0,
            "Words": 0,
            "Lines": 0,
            "Sections found": 0,
            "References found": 0,
            "Title detected": "",
            "Section headers (first 5)": "",
            "Text sample (first 400 chars)": "",
            "Error": str(exc),
            "_full_text": "",
        }


# ─────────────────────────────────────────── Excel writer ────────────────────

SUMMARY_COLS = [
    "Parser", "Status", "Time (ms)", "Chars", "Words", "Lines",
    "Sections found", "References found", "Title detected",
    "Section headers (first 5)", "Text sample (first 400 chars)", "Error",
]

COL_WIDTHS = {
    "Parser": 28,
    "Status": 10,
    "Time (ms)": 12,
    "Chars": 12,
    "Words": 10,
    "Lines": 8,
    "Sections found": 16,
    "References found": 18,
    "Title detected": 40,
    "Section headers (first 5)": 55,
    "Text sample (first 400 chars)": 70,
    "Error": 40,
}

FILL_HEADER  = PatternFill("solid", fgColor="1F4E79")
FILL_OK      = PatternFill("solid", fgColor="E2EFDA")
FILL_ERROR   = PatternFill("solid", fgColor="FFE0E0")
FILL_OCR     = PatternFill("solid", fgColor="FFF2CC")
FILL_SECTION = PatternFill("solid", fgColor="DDEBF7")

FONT_HEADER  = Font(bold=True, color="FFFFFF", size=11)
FONT_BOLD    = Font(bold=True)
THIN         = Side(style="thin", color="BFBFBF")
BORDER       = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP         = Alignment(wrap_text=True, vertical="top")
CENTER       = Alignment(horizontal="center", vertical="top")


def _cell(ws, row, col, value, fill=None, font=None, align=None):
    c = ws.cell(row=row, column=col, value=_sanitize(value))
    c.border = BORDER
    if fill:   c.fill   = fill
    if font:   c.font   = font
    if align:  c.alignment = align
    else:      c.alignment = WRAP
    return c


def write_excel(results: list, path: Path, doc_path: Path):
    wb = openpyxl.Workbook()

    # ── Sheet 1: Summary ──────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Summary"
    ws.freeze_panes = "B2"

    # Title row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(SUMMARY_COLS))
    title_cell = ws.cell(row=1, column=1, value=f"Parser Benchmark — {doc_path.name}")
    title_cell.font = Font(bold=True, size=13, color="FFFFFF")
    title_cell.fill = PatternFill("solid", fgColor="243F60")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 22

    # Header row
    for ci, col_name in enumerate(SUMMARY_COLS, 1):
        _cell(ws, 2, ci, col_name, fill=FILL_HEADER, font=FONT_HEADER, align=CENTER)
    ws.row_dimensions[2].height = 18

    # Data rows
    for ri, row in enumerate(results, 3):
        is_ocr   = row["Parser"].startswith("OCR")
        is_error = row["Status"] == "ERROR"
        row_fill = FILL_ERROR if is_error else (FILL_OCR if is_ocr else FILL_OK)

        for ci, col_name in enumerate(SUMMARY_COLS, 1):
            val = row.get(col_name, "")
            f = FILL_ERROR if is_error else (FILL_SECTION if ci == 1 else row_fill)
            fnt = FONT_BOLD if ci == 1 else None
            _cell(ws, ri, ci, val, fill=f, font=fnt)

        ws.row_dimensions[ri].height = 80 if not is_error else 20

    # Column widths
    for ci, col_name in enumerate(SUMMARY_COLS, 1):
        ws.column_dimensions[get_column_letter(ci)].width = COL_WIDTHS.get(col_name, 15)

    # Conditional colour scale on numeric columns (Time, Chars, Words)
    numeric_cols = {"Time (ms)": 3, "Chars": 4, "Words": 5}
    last_data_row = 2 + len(results)
    for col_name, ci in numeric_cols.items():
        col_letter = get_column_letter(ci)
        cell_range = f"{col_letter}3:{col_letter}{last_data_row}"
        # Green = high (better text extraction), Red = low — reversed for Time
        if col_name == "Time (ms)":
            rule = ColorScaleRule(start_type="min", start_color="63BE7B",
                                  end_type="max",   end_color="F8696B")
        else:
            rule = ColorScaleRule(start_type="min", start_color="F8696B",
                                  end_type="max",   end_color="63BE7B")
        ws.conditional_formatting.add(cell_range, rule)

    # ── Sheet 2: Full extracted text ──────────────────────────────────────────
    ws2 = wb.create_sheet("Full Text")
    ws2.freeze_panes = "A2"

    # header
    _cell(ws2, 1, 1, "Parser",       fill=FILL_HEADER, font=FONT_HEADER, align=CENTER)
    _cell(ws2, 1, 2, "Full Text",    fill=FILL_HEADER, font=FONT_HEADER, align=CENTER)
    _cell(ws2, 1, 3, "Chars",        fill=FILL_HEADER, font=FONT_HEADER, align=CENTER)
    ws2.column_dimensions["A"].width = 28
    ws2.column_dimensions["B"].width = 120
    ws2.column_dimensions["C"].width = 12

    for ri, row in enumerate(results, 2):
        is_ocr   = row["Parser"].startswith("OCR")
        row_fill = FILL_OCR if is_ocr else FILL_OK
        _cell(ws2, ri, 1, row["Parser"], fill=FILL_SECTION, font=FONT_BOLD)
        _cell(ws2, ri, 2, row["_full_text"][:32000], fill=row_fill)  # Excel cell limit
        _cell(ws2, ri, 3, row["Chars"], fill=row_fill, align=CENTER)
        ws2.row_dimensions[ri].height = 400

    # ── Sheet 3: Parser descriptions ─────────────────────────────────────────
    ws3 = wb.create_sheet("Parser Info")
    _cell(ws3, 1, 1, "Parser",      fill=FILL_HEADER, font=FONT_HEADER, align=CENTER)
    _cell(ws3, 1, 2, "Category",    fill=FILL_HEADER, font=FONT_HEADER, align=CENTER)
    _cell(ws3, 1, 3, "Description", fill=FILL_HEADER, font=FONT_HEADER, align=CENTER)
    ws3.column_dimensions["A"].width = 28
    ws3.column_dimensions["B"].width = 18
    ws3.column_dimensions["C"].width = 60

    all_parsers = PARSERS + OCR_PARSERS
    for ri, (name, _, desc) in enumerate(all_parsers, 2):
        cat = "OCR" if name.startswith("OCR") else "Text layer"
        _cell(ws3, ri, 1, name, fill=FILL_SECTION, font=FONT_BOLD)
        _cell(ws3, ri, 2, cat,  fill=FILL_OK, align=CENTER)
        _cell(ws3, ri, 3, desc, fill=FILL_OK)
        ws3.row_dimensions[ri].height = 18

    wb.save(path)
    print(f"\n  Saved → {path}")


# ─────────────────────────────────────────── main ────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Benchmark Agent 1 parsing backends")
    ap.add_argument("document", help="Path to PDF (or DOCX/HTML/TXT)")
    ap.add_argument("--ocr",  action="store_true", help="Also run OCR engines (slow)")
    ap.add_argument("--out",  default="", help="Output Excel path (default: data/output/)")
    args = ap.parse_args()

    doc_path = Path(args.document)
    if not doc_path.exists():
        print(f"Error: file not found: {doc_path}")
        sys.exit(1)

    out_path = Path(args.out) if args.out else Path("data/output") / f"parser_benchmark_{doc_path.stem}.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    parsers_to_run = list(PARSERS)
    if args.ocr:
        parsers_to_run += OCR_PARSERS

    print(f"\n=== Agent 1 Parser Benchmark ===")
    print(f"  Document : {doc_path}")
    print(f"  Parsers  : {len(parsers_to_run)}  (--ocr={'yes' if args.ocr else 'no'})")
    print(f"  Output   : {out_path}\n")

    results = []
    for name, fn, _ in parsers_to_run:
        results.append(run_one(name, fn, doc_path))

    write_excel(results, out_path, doc_path)

    # Quick console summary
    print("\n┌─ Quick summary ─────────────────────────────────────────────┐")
    header = f"{'Parser':<28} {'Status':<8} {'ms':>6} {'Chars':>8} {'Words':>7} {'Secs':>5} {'Refs':>5}"
    print(f"│ {header} │")
    print("├" + "─" * 67 + "┤")
    for r in results:
        line = (f"{r['Parser']:<28} {r['Status']:<8} {r['Time (ms)']:>6} "
                f"{r['Chars']:>8,} {r['Words']:>7,} {r['Sections found']:>5} {r['References found']:>5}")
        print(f"│ {line} │")
    print("└" + "─" * 67 + "┘")


if __name__ == "__main__":
    main()
