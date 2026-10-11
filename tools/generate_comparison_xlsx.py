"""
Generates pdf_parsers_comparison.xlsx from latest benchmark results.
Run from the knowledge-graph root:
    python tools/generate_comparison_xlsx.py
"""

import json
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "output"
XLSX_PATH = OUTPUT_DIR / "pdf_parsers_comparison.xlsx"

# ── colours ──────────────────────────────────────────────────────────────────
C_HEADER    = "1F4E79"   # dark navy
C_FIELD     = "2E75B6"   # medium blue
C_ALT       = "D6E4F0"   # light blue
C_WHITE     = "FFFFFF"
C_OK        = "E2EFDA"   # light green
C_WARN      = "FFF2CC"   # light yellow
C_BAD       = "FCE4D6"   # light red
C_GOLD      = "FFD700"   # gold  — best overall
C_GOLD_BG   = "FFF3B0"   # pale gold — best cell highlight
C_SILVER    = "C0C0C0"   # silver header — runner-up
C_SILVER_BG = "F0F0F0"   # pale silver

THIN = Side(border_style="thin", color="AAAAAA")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
THICK_GOLD = Side(border_style="medium", color="B8860B")
BORDER_GOLD = Border(left=THICK_GOLD, right=THICK_GOLD,
                     top=THICK_GOLD, bottom=THICK_GOLD)


def hfill(color):
    return PatternFill(start_color=color, end_color=color, fill_type="solid")


def apply_header(cell):
    cell.fill = hfill(C_HEADER)
    cell.font = Font(color=C_WHITE, bold=True)
    cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    cell.border = BORDER


def apply_header_best(cell, label=""):
    """Gold header for the best-in-category column."""
    cell.fill = hfill(C_GOLD)
    cell.font = Font(color="000000", bold=True)
    cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    cell.border = BORDER_GOLD
    if label:
        cell.value = f"★ {cell.value or ''}\n({label})"


def apply_header_runner(cell):
    """Silver header for runner-up column."""
    cell.fill = hfill(C_SILVER)
    cell.font = Font(color="000000", bold=True)
    cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    cell.border = BORDER


def apply_best_cell(cell):
    """Gold background for the single best value in a row."""
    cell.fill = hfill(C_GOLD_BG)
    cell.font = Font(bold=True)
    cell.border = BORDER_GOLD


def apply_field(cell):
    cell.fill = hfill(C_FIELD)
    cell.font = Font(color=C_WHITE, bold=True)
    cell.alignment = Alignment(wrap_text=True, vertical="center")
    cell.border = BORDER


def apply_data(cell, alt=False):
    if alt:
        cell.fill = hfill(C_ALT)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    cell.border = BORDER


def apply_status(cell, value):
    """Colour-code ✅ / ⚠ / ❌ cells."""
    v = str(value)
    if v.startswith("✅"):
        cell.fill = hfill(C_OK)
    elif v.startswith("⚠"):
        cell.fill = hfill(C_WARN)
    elif v.startswith("❌"):
        cell.fill = hfill(C_BAD)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    cell.border = BORDER


def write_table(ws, headers, rows, field_col=0, status_cols=None, col_widths=None):
    """Write a header row + data rows with consistent styling."""
    status_cols = status_cols or []
    for c, h in enumerate(headers, 1):
        apply_header(ws.cell(row=1, column=c, value=h))

    for r, row in enumerate(rows, 2):
        alt = r % 2 == 1
        for c, val in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=val)
            if c - 1 == field_col:
                apply_field(cell)
            elif (c - 1) in status_cols:
                apply_status(cell, val)
            else:
                apply_data(cell, alt)

    if col_widths:
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 28


# ── load JSON results ─────────────────────────────────────────────────────────
def load(name):
    p = OUTPUT_DIR / name
    return json.loads(p.read_text()) if p.exists() else {}


regex    = load("agent1_regex_result.json")
pymupdf  = load("agent1_pymupdf_enhanced_result.json")
marker   = load("agent1_marker_result.json")
pdfplumb = load("agent1_pdfplumber_result.json")
docling  = load("agent1_docling_result.json")
mineru   = load("agent1_mineru_result.json")
cermine  = load("agent1_cermine_result.json")
a3bench  = load("agent3_model_benchmark.json")

CORRECT_TITLE = (
    "Boosting school staff well-being and engagement through identity leadership: "
    "The mediating role of organizational climate"
)

def trunc(s, n=300):
    s = str(s or "—").strip()
    return (s[:n] + "…") if len(s) > n else s


# ── workbook ──────────────────────────────────────────────────────────────────
wb = openpyxl.Workbook()

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 1 — Extraction Comparison
# ══════════════════════════════════════════════════════════════════════════════
ws1 = wb.active
ws1.title = "Extraction Comparison"
ws1.sheet_view.showGridLines = False

PARSERS = ["Regex", "PyMuPDF Enhanced", "Marker", "pdfplumber", "Docling", "MinerU", "CERMINE"]

docling_abstract = trunc(docling.get("abstract", "") or "", 300)
mineru_abstract  = trunc(mineru.get("abstract", "")  or "", 300)
marker_abstract  = trunc(marker.get("abstract", "")  or "", 300)
cermine_abstract = trunc(cermine.get("abstract", "") or "", 300)

cermine_authors = ", ".join(cermine.get("authors", [])) or "—"
cermine_doi     = cermine.get("doi", "") or "—"
cermine_recv    = cermine.get("date_received", "") or "—"
cermine_acc     = cermine.get("date_accepted", "") or "—"

rows_extraction = [
    ["TITLE",
     CORRECT_TITLE, CORRECT_TITLE, CORRECT_TITLE, CORRECT_TITLE,
     "A R T I C L E  ⚠ (header noise)",
     CORRECT_TITLE,
     CORRECT_TITLE],
    ["AUTHORS",
     "—",
     "A R T I C L E, Diana Cárdenas, Bethany Reid, Haochen Zhou, Katherine J. Reynolds, Abstract  ⚠ noise",
     "Diana Cárdenas, Bethany Reid, Haochen Zhou, Katherine J. Reynolds",
     "—", "—", "—",
     cermine_authors + "  ⚠ encoding: á→?"],
    ["DOI",
     "—",
     "10.1111/joop.12513",
     "—",
     "⚠ 10.1111/(ISSN)2044-8325  (wrong — ISSN not DOI)",
     "10.1111/joop.12513",
     "⚠ 10.1016/j  (partial)",
     cermine_doi],
    ["DATE (Received)",
     "7 November 2023", "7 November 2023", "—", "—", "—", "—",
     cermine_recv + "  ⚠ numeric only"],
    ["DATE (Accepted)",
     "7 May 2024", "7 May 2024", "—", "—", "—", "—",
     cermine_acc + "  ⚠ numeric only"],
    ["ABSTRACT",
     "—",
     trunc(pymupdf.get("abstract", "") or "", 300),
     marker_abstract or "—",
     "—",
     docling_abstract or "—",
     mineru_abstract or "—",
     cermine_abstract or "—"],
    ["KEYWORDS",
     "—", "—",
     marker.get("keywords") or "—",
     "—",
     docling.get("keywords") or "—",
     mineru.get("keywords") or "—",
     "—"],
    ["# SECTIONS",
     str(len(regex.get("sections", []))),
     str(len(pymupdf.get("sections", []))),
     str(len(marker.get("sections", []))),
     str(len(pdfplumb.get("sections", []))),
     str(len(docling.get("sections", []))),
     str(len(mineru.get("sections", []))),
     str(cermine.get("section_count", len(cermine.get("sections", [])))) + "  ⚠ noisy (tables+refs mixed in)"],
    ["# REFERENCES",
     str(len(regex.get("references", []))),
     str(len(pymupdf.get("references", []))),
     str(marker.get("reference_count", 0)),
     str(pdfplumb.get("reference_count", 0)),
     str(len(docling.get("references", []))),
     str(len(mineru.get("references", []))),
     str(cermine.get("reference_count", len(cermine.get("references", [])))) + "  ❌ fragmented"],
    ["WORD COUNT",
     "12,969", "12,969",
     f"{marker.get('word_count', '—'):,}" if isinstance(marker.get("word_count"), int) else "13,730",
     f"{pdfplumb.get('word_count', '—'):,}" if isinstance(pdfplumb.get("word_count"), int) else "13,678",
     f"{docling.get('word_count', 0):,}",
     f"{mineru.get('word_count', 0):,}",
     f"{cermine.get('word_count', 0):,}"],
    ["TABLES DETECTED",
     "—", "—", "—",
     f"✅ {pdfplumb.get('table_count', 34)} tables",
     "—", "—", "—"],
]

write_table(
    ws1,
    headers=["FIELD"] + PARSERS,
    rows=rows_extraction,
    field_col=0,
    col_widths=[18, 32, 36, 30, 28, 30, 28, 32],
)

# ── mark best columns (header row = 1) ───────────────────────────────────────
# Col indices: 1=FIELD 2=Regex 3=PyMuPDF Enhanced 4=Marker 5=pdfplumber
#              6=Docling 7=MinerU 8=CERMINE
BEST_COL_LABELS_S1 = {
    3: ("SILVER", "best local balance"),
    5: ("SILVER", "best for tables"),
    7: ("GOLD",   "best text & refs"),
    8: ("GOLD",   "best metadata"),
}
for col, (tier, label) in BEST_COL_LABELS_S1.items():
    cell = ws1.cell(row=1, column=col)
    if tier == "GOLD":
        cell.fill   = hfill(C_GOLD)
        cell.font   = Font(color="000000", bold=True)
        cell.border = BORDER_GOLD
        cell.value  = f"★ {cell.value}\n({label})"
    else:
        cell.fill   = hfill(C_SILVER)
        cell.font   = Font(color="000000", bold=True)
        cell.value  = f"▲ {cell.value}\n({label})"
    cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")

# ── mark best cell per row ────────────────────────────────────────────────────
# (sheet_row, col): row 1=header, data starts row 2
BEST_CELLS_S1 = {
    2:  8,   # TITLE        → CERMINE (and most others, but mark CERMINE as scholarly)
    3:  4,   # AUTHORS      → Marker (clean, with ORCID)
    4:  8,   # DOI          → CERMINE (and PyMuPDF Enhanced)
    5:  8,   # DATE recv    → CERMINE (only one with dates)
    6:  8,   # DATE acc     → CERMINE
    7:  8,   # ABSTRACT     → CERMINE (scholarly extraction)
    9:  3,   # # SECTIONS   → PyMuPDF Enhanced (27 clean)
    10: 7,   # # REFERENCES → MinerU (structured)
    12: 5,   # TABLES       → pdfplumber (only one)
}
for srow, col in BEST_CELLS_S1.items():
    c = ws1.cell(row=srow, column=col)
    c.fill   = hfill(C_GOLD_BG)
    c.font   = Font(bold=True)
    c.border = BORDER_GOLD

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 2 — Speed & RAM
# ══════════════════════════════════════════════════════════════════════════════
ws2 = wb.create_sheet("Speed & RAM")
ws2.sheet_view.showGridLines = False

SPEED_PARSERS = ["Regex", "PyMuPDF Enhanced", "Marker", "pdfplumber", "Unstructured.io", "REBEL", "CERMINE"]

rows_speed = [
    ["Type",
     "Rules",
     "Rules + font analysis",
     "Vision Transformer",
     "Rules + layout",
     "CV + OCR",
     "BART seq2seq",
     "ML scholarly (REST API)"],
    ["Time (26-page PDF)",
     "1.25 s", "2.07 s", "140 s", "8.35 s",
     "❌ broken (numpy 2.x)",
     "4.14 s",
     "~157 s (REST API, network)"],
    ["Peak RAM",
     "17.1 MB", "26.8 MB", "590.6 MB", "166.6 MB",
     "❌", "15.7 MB",
     "~0 MB local (server-side)"],
    ["Word Count extracted",
     "13,063", "12,969", "13,730", "13,678",
     "❌", "N/A",
     "9,451"],
]

write_table(
    ws2,
    headers=["METRIC"] + SPEED_PARSERS,
    rows=rows_speed,
    field_col=0,
    col_widths=[22, 18, 22, 16, 16, 22, 16, 28],
)

# Col indices: 1=METRIC 2=Regex 3=PyMuPDF Enhanced 4=Marker
#              5=pdfplumber 6=Unstructured 7=REBEL 8=CERMINE
BEST_COL_LABELS_S2 = {
    2: ("GOLD",   "fastest"),
    3: ("SILVER", "best balance"),
}
for col, (tier, label) in BEST_COL_LABELS_S2.items():
    cell = ws2.cell(row=1, column=col)
    if tier == "GOLD":
        cell.fill   = hfill(C_GOLD);   cell.font = Font(color="000000", bold=True)
        cell.border = BORDER_GOLD;     cell.value = f"★ {cell.value}\n({label})"
    else:
        cell.fill   = hfill(C_SILVER); cell.font = Font(color="000000", bold=True)
        cell.value  = f"▲ {cell.value}\n({label})"
    cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")

# best cells: time row=2 col=2 (Regex), RAM row=3 col=2, words row=4 col=3
for srow, col in [(2, 2), (3, 2), (4, 3)]:
    c = ws2.cell(row=srow, column=col)
    c.fill = hfill(C_GOLD_BG); c.font = Font(bold=True); c.border = BORDER_GOLD

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 3 — Feature Matrix
# ══════════════════════════════════════════════════════════════════════════════
ws3 = wb.create_sheet("Feature Matrix")
ws3.sheet_view.showGridLines = False

FEAT_PARSERS = ["Regex", "PyMuPDF Enhanced", "Marker", "pdfplumber", "REBEL", "CERMINE"]

rows_features = [
    ["Title",              "✅",        "✅",            "✅",         "✅",              "❌ n/a",  "✅"],
    ["Authors",            "❌",        "⚠ + noise",    "✅",         "❌",              "❌",       "⚠ encoding"],
    ["DOI",                "❌",        "✅",            "✅",         "⚠ wrong",        "❌",       "✅"],
    ["Dates (received/accepted)", "✅", "✅",            "❌",         "❌",              "❌",       "⚠ numeric"],
    ["Abstract",           "❌",        "✅",            "❌",         "❌",              "❌",       "✅"],
    ["Keywords",           "❌",        "❌",            "✅",         "❌",              "❌",       "❌"],
    ["TOC with levels",    "❌",        "✅ full",       "❌",         "❌",              "❌",       "❌"],
    ["Sections",           "⚠ noisy",  "✅ 27 clean",  "✅ clean",   "⚠ noisy/garbled","❌",       "⚠ 23 noisy"],
    ["Tables detected",    "❌",        "❌",            "❌",         "✅ 34 tables",    "❌",       "❌"],
    ["References",         "⚠ raw",    "⚠ noisy",      "⚠ struct.",  "✅ 401 lines",    "❌",       "❌ 14 fragmented"],
    ["Relations (triplets)","❌",       "❌",            "❌",         "❌",              "✅ subj→rel→obj", "❌"],
]

write_table(
    ws3,
    headers=["FEATURE"] + FEAT_PARSERS,
    rows=rows_features,
    field_col=0,
    status_cols=[1, 2, 3, 4, 5, 6],
    col_widths=[24, 14, 22, 16, 20, 22, 22],
)

# Col: 1=FEATURE 2=Regex 3=PyMuPDF Enhanced 4=Marker 5=pdfplumber 6=REBEL 7=CERMINE
# Best column per feature (row): mark the winning cell gold
# row 2=Title, 3=Authors, 4=DOI, 5=Dates, 6=Abstract, 7=Keywords,
# 8=TOC, 9=Sections, 10=Tables, 11=References, 12=Relations
BEST_CELLS_S3 = {
    3:  4,   # Authors    → Marker
    4:  7,   # DOI        → CERMINE (tie w/ PyMuPDF, pick scholarly)
    5:  3,   # Dates      → PyMuPDF Enhanced
    6:  7,   # Abstract   → CERMINE
    7:  4,   # Keywords   → Marker
    8:  3,   # TOC        → PyMuPDF Enhanced
    9:  3,   # Sections   → PyMuPDF Enhanced
    10: 5,   # Tables     → pdfplumber
    11: 5,   # References → pdfplumber
    12: 6,   # Relations  → REBEL
}
# Gold column headers for most-capable parsers in feature matrix
for col, (tier, label) in {3: ("SILVER","best local"), 7: ("GOLD","best metadata")}.items():
    cell = ws3.cell(row=1, column=col)
    if tier == "GOLD":
        cell.fill = hfill(C_GOLD); cell.font = Font(color="000000", bold=True)
        cell.border = BORDER_GOLD; cell.value = f"★ {cell.value}\n({label})"
    else:
        cell.fill = hfill(C_SILVER); cell.font = Font(color="000000", bold=True)
        cell.value = f"▲ {cell.value}\n({label})"
    cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")

for srow, col in BEST_CELLS_S3.items():
    c = ws3.cell(row=srow, column=col)
    c.fill = hfill(C_GOLD_BG); c.font = Font(bold=True); c.border = BORDER_GOLD

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 4 — Section Lists
# ══════════════════════════════════════════════════════════════════════════════
ws4 = wb.create_sheet("Section Lists")
ws4.sheet_view.showGridLines = False

sec_lists = {
    "Regex":            regex.get("sections", []),
    "PyMuPDF Enhanced": pymupdf.get("sections", []),
    "Marker":           marker.get("sections", []),
    "pdfplumber":       pdfplumb.get("sections", []),
    "Docling":          docling.get("sections", []),
    "MinerU":           mineru.get("sections", []),
    "CERMINE":          cermine.get("sections", []),
}

max_secs = max(len(v) for v in sec_lists.values())
sec_headers = ["#"] + list(sec_lists.keys())
for c, h in enumerate(sec_headers, 1):
    apply_header(ws4.cell(row=1, column=c, value=h))

for i in range(max_secs):
    alt = (i + 1) % 2 == 0
    ws4.cell(row=i + 2, column=1, value=i + 1).border = BORDER
    for c, secs in enumerate(sec_lists.values(), 2):
        cell = ws4.cell(row=i + 2, column=c, value=secs[i] if i < len(secs) else "")
        apply_data(cell, alt)

ws4.column_dimensions["A"].width = 5
for col in range(2, len(sec_headers) + 1):
    ws4.column_dimensions[get_column_letter(col)].width = 30
ws4.row_dimensions[1].height = 28

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 5 — References Sample
# ══════════════════════════════════════════════════════════════════════════════
ws5 = wb.create_sheet("References Sample")
ws5.sheet_view.showGridLines = False

ref_lists = {
    "Regex":            regex.get("references", []),
    "PyMuPDF Enhanced": pymupdf.get("references", []),
    "Marker":           [],   # 0 references extracted
    "pdfplumber":       (pdfplumb.get("references_sample") or pdfplumb.get("references") or []),
    "Docling":          docling.get("references", []),
    "MinerU":           mineru.get("references", []),
    "CERMINE":          cermine.get("references", []),
}

SAMPLE = 20
ref_headers = ["#"] + list(ref_lists.keys())
for c, h in enumerate(ref_headers, 1):
    apply_header(ws5.cell(row=1, column=c, value=h))

for i in range(SAMPLE):
    alt = (i + 1) % 2 == 0
    ws5.cell(row=i + 2, column=1, value=i + 1).border = BORDER
    for c, refs in enumerate(ref_lists.values(), 2):
        cell = ws5.cell(row=i + 2, column=c, value=refs[i] if i < len(refs) else "")
        apply_data(cell, alt)

ws5.column_dimensions["A"].width = 5
for col in range(2, len(ref_headers) + 1):
    ws5.column_dimensions[get_column_letter(col)].width = 40
ws5.row_dimensions[1].height = 28

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 6 — Tool Overview
# ══════════════════════════════════════════════════════════════════════════════
ws6 = wb.create_sheet("Tool Overview")
ws6.sheet_view.showGridLines = False

tool_headers = [
    "Technology", "Category", "Type", "Popularity",
    "Speed (pages/sec)", "Fits Scientific Papers",
    "Released", "Last Updated", "Test Time", "Test RAM (MB)", "Status",
    "★ Best for",
]

tool_rows = [
    ["Granite Docling", "PDF Parser", "Open-source VLM",
     "New, no strong OSS signal yet", "Not public", "Very good",
     "Jul 2024", "Apr 2026", "Not tested", "—", "Not tested", "—"],
    ["Docling", "PDF Parser", "Open-source doc conversion toolkit",
     "~58.8k ⭐", "Not public", "Very good",
     "Jul 2024", "Apr 2026", "89.53 s", "369.3", "✅ Tested",
     "Structured references"],
    ["MinerU", "PDF Parser", "Open-source PDF parser",
     "~60.3k ⭐", "Not public", "Very good",
     "Feb 2024", "Apr 2026", "~200 s", "764.8", "✅ Tested",
     "★ Best text quality + structured refs"],
    ["Marker", "PDF Parser", "Open-source PDF→Markdown/JSON",
     "~34k ⭐", "~5.56 pages/process", "Good–Very good",
     "Oct 2023", "Apr 2026", "140 s", "590.6", "✅ Tested",
     "Clean body text + author extraction"],
    ["GROBID", "PDF Parser", "Scholarly ML parser",
     "~4.8k ⭐, large academic adoption",
     "~231 pp/s large scale; ~2.5 PDF/s small machine",
     "Very good for born-digital",
     "Sep 2012", "Apr 2026", "Needs Docker", "—", "❌ Needs Docker",
     "High-volume scholarly pipelines (Docker)"],
    ["CERMINE", "PDF Parser", "Scholarly ML parser — JATS XML output",
     "~511 ⭐", "Not public", "Good (weak on references)",
     "Oct 2012", "Apr 2026", "~157 s (REST API)", "~0 (server-side)", "✅ Tested",
     "★ Best metadata (title/authors/DOI/dates/abstract)"],
    ["Nougat", "PDF Parser", "AI OCR model for academic PDFs",
     "~9.9k ⭐", "Not public", "Good–Very good",
     "Jun 2023", "Apr 2026", "—", "—", "❌ Incompatible", "—"],
    ["Unstructured", "PDF Parser", "Open-source ETL/partitioning library",
     "~14.6k ⭐", "Not public", "Moderate",
     "Sep 2022", "Apr 2026", "❌ broken", "—", "❌ broken (numpy 2.x)", "—"],
    ["ParsCit", "PDF Parser", "Legacy citation parser",
     "Legacy, no strong current signal", "Not public", "Limited",
     "Jul 2010", "Feb 2026", "Not tested", "—", "Not tested", "—"],
    ["Regex / PyMuPDF", "PDF Parser", "Rules-based",
     "~7k ⭐", "Fast", "Moderate",
     "Oct 2012", "Apr 2026", "1.25 s", "17.1", "✅ Tested",
     "★ Fastest — high-volume pipelines"],
    ["PyMuPDF Enhanced", "PDF Parser", "Rules + font/TOC analysis",
     "~7k ⭐", "Fast", "Good",
     "Oct 2012", "Apr 2026", "2.07 s", "26.8", "✅ Tested",
     "★ Best local balance — speed + sections + DOI"],
    ["pdfplumber", "PDF Parser", "Rules-based layout analysis",
     "~10.2k ⭐", "Medium", "Moderate",
     "Aug 2015", "Apr 2026", "8.35 s", "166.6", "✅ Tested",
     "★ Only tool that detects tables"],
    ["SciBERT", "NLP Model", "BERT pre-trained on 1.14M scientific papers; used as KeyBERT backbone",
     "~1.7k ⭐", "Not applicable", "Very good",
     "Sep 2019", "Not maintained",
     f"{a3bench.get('keybert_scibert',{}).get('time_s','—')} s",
     str(a3bench.get('keybert_scibert',{}).get('peak_ram_mb','—')),
     "✅ Tested (Agent 3)",
     "Fast & lightweight keyphrase extraction (Agent 3)"],
    ["SciSpacy", "NLP Model", "spaCy NER pipeline trained on biomedical/scientific text",
     "~1.9k ⭐", "Not applicable", "Very good",
     "May 2019", "Oct 2025",
     f"{a3bench.get('scispacy_en_core_sci_sm',{}).get('time_s','—')} s",
     str(a3bench.get('scispacy_en_core_sci_sm',{}).get('peak_ram_mb','—')),
     "✅ Tested (Agent 3)",
     "★ Most entities found — scientific NER (Agent 3)"],
    ["REBEL", "NLP Model", "BART seq2seq relation extraction",
     "Not public", "Not applicable", "Good",
     "Nov 2021", "Active", "4.14 s", "15.7", "Agent 4",
     "★ Only tool for relation extraction (Agent 4)"],
]

write_table(
    ws6,
    headers=tool_headers,
    rows=tool_rows,
    field_col=0,
    status_cols=[10],
    col_widths=[18, 12, 36, 30, 42, 22, 10, 14, 14, 14, 22, 36],
)

# ── gold header for "Best for" column (col 12) ───────────────────────────────
best_hdr = ws6.cell(row=1, column=12)
best_hdr.fill   = hfill(C_GOLD)
best_hdr.font   = Font(color="000000", bold=True)
best_hdr.border = BORDER_GOLD
best_hdr.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")

# ── highlight rows whose "Best for" starts with ★ ────────────────────────────
for ri, row in enumerate(tool_rows, 2):
    best_val = row[-1]
    if best_val.startswith("★"):
        # Gold background on the Technology name cell and Best for cell
        for col in [1, 12]:
            c = ws6.cell(row=ri, column=col)
            c.fill   = hfill(C_GOLD_BG)
            c.font   = Font(bold=True)
            c.border = BORDER_GOLD

# ══════════════════════════════════════════════════════════════════════════════
# Sheet 7 — Agent 3: Concept Extraction (SciBERT benchmark)
# ══════════════════════════════════════════════════════════════════════════════
ws7 = wb.create_sheet("Agent 3 – Concept Extraction")
ws7.sheet_view.showGridLines = False

A3_MODELS = [
    ("spaCy\nen_core_web_sm",      "spacy_en_core_web_sm"),
    ("SciSpacy\nen_core_sci_sm",   "scispacy_en_core_sci_sm"),
    ("KeyBERT\nbge-small",         "keybert_bge_small"),
    ("KeyBERT\n+ SciBERT ★",       "keybert_scibert"),
    ("YAKE\n(statistical)",        "yake"),
]

# ── metrics block ─────────────────────────────────────────────────────────────
metric_headers = ["METRIC"] + [m for m, _ in A3_MODELS]
for ci, (h, (_, key)) in enumerate(zip(metric_headers[1:], A3_MODELS), 2):
    cell = ws7.cell(row=1, column=ci, value=h)
    if key == "keybert_bge_small":
        cell.fill = hfill(C_GOLD);   cell.font = Font(color="000000", bold=True)
        cell.border = BORDER_GOLD;   cell.value = f"★ {h}\n(best quality)"
    elif key == "yake":
        cell.fill = hfill(C_SILVER); cell.font = Font(color="000000", bold=True)
        cell.value = f"▲ {h}\n(fastest)"
    elif key == "scispacy_en_core_sci_sm":
        cell.fill = hfill(C_GOLD);   cell.font = Font(color="000000", bold=True)
        cell.border = BORDER_GOLD;   cell.value = f"★ {h}\n(most entities)"
    else:
        apply_header(cell)
    cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")

apply_header(ws7.cell(row=1, column=1, value="METRIC"))
ws7.row_dimensions[1].height = 42

# best metric cells: Concepts→SciSpacy(col3), Time→YAKE(col6), RAM→YAKE(col6)
A3_BEST_METRIC_CELLS = [(3, 3), (4, 6), (5, 6)]  # (sheet_row, col)
for srow, col in A3_BEST_METRIC_CELLS:
    c = ws7.cell(row=srow, column=col)
    c.fill = hfill(C_GOLD_BG); c.font = Font(bold=True); c.border = BORDER_GOLD

metric_rows = [
    ("Category",        ["NER", "NER (scientific)", "Keyphrase", "Keyphrase", "Keyword"]),
    ("Approach",        ["Rules + ML", "Rules + ML (sci)", "Embedding similarity", "SciBERT embedding", "Statistical"]),
    ("Concepts found",  [a3bench.get(k, {}).get("concept_count", "—") for _, k in A3_MODELS]),
    ("Time (s)",        [a3bench.get(k, {}).get("time_s", "—") for _, k in A3_MODELS]),
    ("Peak RAM (MB)",   [a3bench.get(k, {}).get("peak_ram_mb", "—") for _, k in A3_MODELS]),
]

for ri, (label, vals) in enumerate(metric_rows, 2):
    apply_field(ws7.cell(row=ri, column=1, value=label))
    for ci, (val, (_, key)) in enumerate(zip(vals, A3_MODELS), 2):
        cell = ws7.cell(row=ri, column=ci, value=val)
        is_scibert = "scibert" in key or "scispacy" in key
        cell.fill = hfill("F4E6FF" if is_scibert else C_ALT)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.border = BORDER

ws7.row_dimensions[6].height = 4  # small spacer

# ── top concepts block ────────────────────────────────────────────────────────
concept_row_start = 8
for c, (m, _) in enumerate([(""  , "")] + A3_MODELS, 1):
    apply_header(ws7.cell(row=concept_row_start, column=c, value="TOP CONCEPTS" if c == 1 else m))
ws7.row_dimensions[concept_row_start].height = 32

TOP = 15
for i in range(TOP):
    alt = (i + 1) % 2 == 0
    ws7.cell(row=concept_row_start + 1 + i, column=1, value=i + 1).border = BORDER
    for ci, (_, key) in enumerate(A3_MODELS, 2):
        sample = a3bench.get(key, {}).get("sample", [])
        val    = sample[i] if i < len(sample) else ""
        cell   = ws7.cell(row=concept_row_start + 1 + i, column=ci, value=val)
        is_sci = "scibert" in key or "scispacy" in key
        cell.fill   = hfill("F4E6FF" if is_sci else (C_ALT if alt else C_WHITE))
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.border = BORDER

# ── overlap block ─────────────────────────────────────────────────────────────
ov = a3bench.get("_overlap", {})
ov_row_start = concept_row_start + TOP + 3

apply_header(ws7.cell(row=ov_row_start, column=1, value="OVERLAP ANALYSIS"))
apply_header(ws7.cell(row=ov_row_start, column=2, value="VALUE"))
ws7.merge_cells(start_row=ov_row_start, start_column=2,
                end_row=ov_row_start, end_column=len(A3_MODELS) + 1)

ov_rows = [
    ("NER: shared concepts (spaCy ∩ SciSpacy)",    ov.get("ner_shared", "—")),
    ("NER: only in spaCy",                          ov.get("ner_only_spacy", "—")),
    ("NER: only in SciSpacy",                       ov.get("ner_only_scispacy", "—")),
    ("Keyphrases: shared (bge-small ∩ SciBERT)",    ov.get("kp_shared", "—")),
    ("Keyphrases: only in bge-small",               ov.get("kp_only_bge", "—")),
    ("Keyphrases: only in SciBERT",                 ov.get("kp_only_scibert", "—")),
    ("Unique to SciBERT (sample)",                  ", ".join(ov.get("kp_unique_scibert_sample", [])[:8])),
    ("Unique to SciSpacy (sample)",                 ", ".join(ov.get("ner_unique_scispacy_sample", [])[:8])),
]
for ri, (label, val) in enumerate(ov_rows, ov_row_start + 1):
    apply_field(ws7.cell(row=ri, column=1, value=label))
    is_sci = "SciBERT" in label or "SciSpacy" in label
    cell = ws7.cell(row=ri, column=2, value=val)
    cell.fill  = hfill("F4E6FF" if is_sci else C_ALT)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    cell.border = BORDER
    ws7.merge_cells(start_row=ri, start_column=2,
                    end_row=ri, end_column=len(A3_MODELS) + 1)
    ws7.row_dimensions[ri].height = 22

# column widths
ws7.column_dimensions["A"].width = 30
for ci in range(2, len(A3_MODELS) + 2):
    ws7.column_dimensions[get_column_letter(ci)].width = 26

# ── save ──────────────────────────────────────────────────────────────────────
wb.save(XLSX_PATH)
print(f"✅  Saved → {XLSX_PATH}")
print(f"   Sheets: {', '.join(wb.sheetnames)}")
