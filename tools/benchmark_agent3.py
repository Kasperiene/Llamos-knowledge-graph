"""
Benchmark Agent 3 concept extractors on the Cárdenas et al. paper.

Tests:
  A. spaCy en_core_web_sm   — general English NER (current baseline)
  B. SciSpacy en_core_sci_sm — scientific NER
  C. KeyBERT + bge-small     — embedding keyphrases (current baseline)
  D. KeyBERT + SciBERT       — scientific embedding keyphrases
  E. YAKE                    — statistical keywords (no model)

Run from the knowledge-graph root:
    python tools/benchmark_agent3.py
"""

import json
import time
import tracemalloc
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "output"
INPUT_JSON = OUTPUT_DIR / "agent1_pymupdf_enhanced_result.json"
RESULT_JSON = OUTPUT_DIR / "agent3_model_benchmark.json"

TOP_N = 30      # how many concepts each model returns
TEXT_LIMIT = 12_000   # chars sent to KeyBERT (same as production)


# ── helpers ───────────────────────────────────────────────────────────────────

def measure(fn):
    """Run fn(), return (result, elapsed_s, peak_ram_mb)."""
    tracemalloc.start()
    t0 = time.perf_counter()
    result = fn()
    elapsed = round(time.perf_counter() - t0, 2)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, round(peak / 1024 / 1024, 1)


def top_concepts(concepts, n=TOP_N):
    return [c["text"] for c in concepts[:n]]


# ── extractors ────────────────────────────────────────────────────────────────

def run_spacy(text, model_name):
    import spacy
    import warnings
    warnings.filterwarnings("ignore")
    nlp = spacy.load(model_name)
    chunk = 100_000
    entities = []
    for i in range(0, len(text), chunk):
        doc = nlp(text[i:i + chunk])
        for ent in doc.ents:
            entities.append({"text": ent.text.strip(), "label": ent.label_})
    # deduplicate
    seen = {}
    for e in entities:
        k = e["text"].lower()
        if k not in seen:
            seen[k] = e
    result = list(seen.values())
    return result


def run_keybert(text, model_name):
    from keybert import KeyBERT
    kw_model = KeyBERT(model=model_name)
    keywords = kw_model.extract_keywords(
        text[:TEXT_LIMIT],
        keyphrase_ngram_range=(1, 3),
        stop_words="english",
        use_mmr=True,
        diversity=0.5,
        top_n=TOP_N,
    )
    return [{"text": kw, "score": round(score, 4)} for kw, score in keywords]


def run_yake(text):
    import yake
    extractor = yake.KeywordExtractor(lan="en", n=3, dedupLim=0.7, top=TOP_N)
    keywords = extractor.extract_keywords(text)
    if keywords:
        max_s = max(s for _, s in keywords) or 1
        return [{"text": kw, "score": round(1 - s / max_s, 4)} for kw, s in keywords]
    return []


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print("Agent 3 Model Benchmark — Concept Extraction")
    print(f"{'='*60}\n")

    # load paper text
    data = json.loads(INPUT_JSON.read_text())
    text = data["text"]
    print(f"Paper text: {len(text):,} chars | ~{len(text.split()):,} words\n")

    results = {}

    # ── A. spaCy en_core_web_sm ──────────────────────────────────────────────
    print("[A] spaCy en_core_web_sm (general English NER)...")
    concepts_a, t_a, ram_a = measure(lambda: run_spacy(text, "en_core_web_sm"))
    print(f"    {len(concepts_a)} entities | {t_a}s | {ram_a} MB")
    print(f"    Sample: {[c['text'] for c in concepts_a[:8]]}")
    entity_types_a = {}
    for c in concepts_a:
        entity_types_a[c["label"]] = entity_types_a.get(c["label"], 0) + 1
    print(f"    Types: {entity_types_a}")
    results["spacy_en_core_web_sm"] = {
        "model": "en_core_web_sm",
        "type": "spaCy NER (general English)",
        "time_s": t_a,
        "peak_ram_mb": ram_a,
        "concept_count": len(concepts_a),
        "entity_types": entity_types_a,
        "sample": [c["text"] for c in concepts_a[:15]],
    }

    # ── B. SciSpacy en_core_sci_sm ───────────────────────────────────────────
    print("\n[B] SciSpacy en_core_sci_sm (scientific NER)...")
    concepts_b, t_b, ram_b = measure(lambda: run_spacy(text, "en_core_sci_sm"))
    print(f"    {len(concepts_b)} entities | {t_b}s | {ram_b} MB")
    print(f"    Sample: {[c['text'] for c in concepts_b[:8]]}")
    entity_types_b = {}
    for c in concepts_b:
        entity_types_b[c["label"]] = entity_types_b.get(c["label"], 0) + 1
    print(f"    Types: {entity_types_b}")
    results["scispacy_en_core_sci_sm"] = {
        "model": "en_core_sci_sm",
        "type": "SciSpacy NER (scientific)",
        "time_s": t_b,
        "peak_ram_mb": ram_b,
        "concept_count": len(concepts_b),
        "entity_types": entity_types_b,
        "sample": [c["text"] for c in concepts_b[:15]],
    }

    # ── C. KeyBERT + bge-small-en-v1.5 ──────────────────────────────────────
    print("\n[C] KeyBERT + BAAI/bge-small-en-v1.5 (current embedding)...")
    concepts_c, t_c, ram_c = measure(lambda: run_keybert(text, "BAAI/bge-small-en-v1.5"))
    print(f"    {len(concepts_c)} keyphrases | {t_c}s | {ram_c} MB")
    print(f"    Sample: {[c['text'] for c in concepts_c[:8]]}")
    results["keybert_bge_small"] = {
        "model": "BAAI/bge-small-en-v1.5",
        "type": "KeyBERT (general embedding)",
        "time_s": t_c,
        "peak_ram_mb": ram_c,
        "concept_count": len(concepts_c),
        "sample": [c["text"] for c in concepts_c[:15]],
        "scores": [c["score"] for c in concepts_c[:15]],
    }

    # ── D. KeyBERT + SciBERT ─────────────────────────────────────────────────
    print("\n[D] KeyBERT + allenai/scibert_scivocab_uncased (SciBERT)...")
    concepts_d, t_d, ram_d = measure(
        lambda: run_keybert(text, "allenai/scibert_scivocab_uncased")
    )
    print(f"    {len(concepts_d)} keyphrases | {t_d}s | {ram_d} MB")
    print(f"    Sample: {[c['text'] for c in concepts_d[:8]]}")
    results["keybert_scibert"] = {
        "model": "allenai/scibert_scivocab_uncased",
        "type": "KeyBERT + SciBERT (scientific embedding)",
        "time_s": t_d,
        "peak_ram_mb": ram_d,
        "concept_count": len(concepts_d),
        "sample": [c["text"] for c in concepts_d[:15]],
        "scores": [c["score"] for c in concepts_d[:15]],
    }

    # ── E. YAKE ──────────────────────────────────────────────────────────────
    print("\n[E] YAKE (statistical, no model)...")
    concepts_e, t_e, ram_e = measure(lambda: run_yake(text))
    print(f"    {len(concepts_e)} keywords | {t_e}s | {ram_e} MB")
    print(f"    Sample: {[c['text'] for c in concepts_e[:8]]}")
    results["yake"] = {
        "model": "YAKE",
        "type": "Statistical keyword extraction",
        "time_s": t_e,
        "peak_ram_mb": ram_e,
        "concept_count": len(concepts_e),
        "sample": [c["text"] for c in concepts_e[:15]],
    }

    # ── summary table ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"{'Model':<38} {'Concepts':>8} {'Time':>8} {'RAM':>10}")
    print("-" * 68)
    for key, r in results.items():
        print(f"{r['model']:<38} {r['concept_count']:>8} {r['time_s']:>7}s {r['peak_ram_mb']:>8} MB")

    # ── overlap analysis ──────────────────────────────────────────────────────
    set_a = {c["text"].lower() for c in concepts_a}
    set_b = {c["text"].lower() for c in concepts_b}
    overlap_ab = len(set_a & set_b)
    only_a = len(set_a - set_b)
    only_b = len(set_b - set_a)

    set_c = {c["text"].lower() for c in concepts_c}
    set_d = {c["text"].lower() for c in concepts_d}
    overlap_cd = len(set_c & set_d)
    only_c = len(set_c - set_d)
    only_d = len(set_d - set_c)

    print(f"\nNER overlap (spaCy vs SciSpacy):")
    print(f"  Shared: {overlap_ab}  |  Only spaCy: {only_a}  |  Only SciSpacy: {only_b}")
    print(f"  Unique to SciSpacy: {sorted(list(set_b - set_a))[:10]}")

    print(f"\nKeyphrase overlap (bge-small vs SciBERT):")
    print(f"  Shared: {overlap_cd}  |  Only bge-small: {only_c}  |  Only SciBERT: {only_d}")
    print(f"  Unique to SciBERT: {sorted(list(set_d - set_c))[:10]}")

    results["_overlap"] = {
        "ner_shared": overlap_ab,
        "ner_only_spacy": only_a,
        "ner_only_scispacy": only_b,
        "ner_unique_scispacy_sample": sorted(list(set_b - set_a))[:20],
        "kp_shared": overlap_cd,
        "kp_only_bge": only_c,
        "kp_only_scibert": only_d,
        "kp_unique_scibert_sample": sorted(list(set_d - set_c))[:20],
    }

    RESULT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n✅  Results saved → {RESULT_JSON}")

    write_excel(results, concepts_a, concepts_b, concepts_c, concepts_d, concepts_e)


def write_excel(results, concepts_a, concepts_b, concepts_c, concepts_d, concepts_e):
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    XLSX_PATH = OUTPUT_DIR / "agent3_scibert_benchmark.xlsx"

    THIN   = Side(border_style="thin", color="AAAAAA")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    C_HEADER  = "1F4E79"; C_FIELD = "2E75B6"; C_WHITE = "FFFFFF"
    C_ALT     = "D6E4F0"; C_SCIBERT = "F4E6FF"

    def fill(c): return PatternFill(start_color=c, end_color=c, fill_type="solid")
    def hdr(cell, v):
        cell.value = v; cell.fill = fill(C_HEADER)
        cell.font = Font(color=C_WHITE, bold=True)
        cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        cell.border = BORDER
    def fld(cell, v):
        cell.value = v; cell.fill = fill(C_FIELD)
        cell.font = Font(color=C_WHITE, bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = BORDER
    def dat(cell, v, alt=False, scibert=False):
        cell.value = v
        cell.fill = fill(C_SCIBERT if scibert else (C_ALT if alt else C_WHITE))
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.border = BORDER

    MODELS = ["spaCy\nen_core_web_sm", "SciSpacy\nen_core_sci_sm",
              "KeyBERT\nbge-small", "KeyBERT\n+ SciBERT ★", "YAKE\n(statistical)"]
    KEYS   = ["spacy_en_core_web_sm", "scispacy_en_core_sci_sm",
              "keybert_bge_small", "keybert_scibert", "yake"]
    IS_SCI = [False, True, False, True, False]

    wb = openpyxl.Workbook()

    # ── Sheet 1: Summary ────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False

    for c, h in enumerate(["METRIC"] + MODELS, 1):
        hdr(ws.cell(row=1, column=c), h)
    ws.row_dimensions[1].height = 32

    summary_rows = [
        ("Category",       ["NER", "NER (sci)", "Keyphrase", "Keyphrase", "Keyword"]),
        ("Approach",       ["Rules+ML", "Rules+ML (sci)", "Embeddings", "SciBERT embed", "Statistical"]),
        ("Concepts found", [results[k]["concept_count"] for k in KEYS]),
        ("Time (s)",       [results[k]["time_s"] for k in KEYS]),
        ("Peak RAM (MB)",  [results[k]["peak_ram_mb"] for k in KEYS]),
    ]
    for ri, (label, vals) in enumerate(summary_rows, 2):
        fld(ws.cell(row=ri, column=1), label)
        for ci, (v, sci) in enumerate(zip(vals, IS_SCI), 2):
            dat(ws.cell(row=ri, column=ci), v, scibert=sci)

    ws.column_dimensions["A"].width = 18
    for ci in range(2, 7):
        ws.column_dimensions[get_column_letter(ci)].width = 22

    # ── Sheet 2: Top Concepts Side-by-Side ──────────────────────────────────────
    ws2 = wb.create_sheet("Top Concepts")
    ws2.sheet_view.showGridLines = False

    for c, h in enumerate(["#"] + MODELS, 1):
        hdr(ws2.cell(row=1, column=c), h)
    ws2.row_dimensions[1].height = 32

    all_concepts = [concepts_a, concepts_b, concepts_c, concepts_d, concepts_e]
    for i in range(TOP_N):
        alt = (i + 1) % 2 == 0
        ws2.cell(row=i+2, column=1, value=i+1).border = BORDER
        for ci, (concepts, sci) in enumerate(zip(all_concepts, IS_SCI), 2):
            v = concepts[i]["text"] if i < len(concepts) else ""
            dat(ws2.cell(row=i+2, column=ci), v, alt=alt, scibert=sci)

    ws2.column_dimensions["A"].width = 5
    for ci in range(2, 7):
        ws2.column_dimensions[get_column_letter(ci)].width = 35

    # ── Sheet 3: KeyBERT bge-small vs SciBERT ───────────────────────────────────
    ws3 = wb.create_sheet("KeyBERT vs SciBERT")
    ws3.sheet_view.showGridLines = False

    for c, h in enumerate(["#","KeyBERT bge-small","Score","KeyBERT + SciBERT ★","Score","Unique to SciBERT"], 1):
        hdr(ws3.cell(row=1, column=c), h)
    ws3.row_dimensions[1].height = 20

    set_c = {c["text"].lower() for c in concepts_c}
    set_d = {c["text"].lower() for c in concepts_d}
    unique_scibert = [c for c in concepts_d if c["text"].lower() not in set_c]

    for i in range(TOP_N):
        alt = (i + 1) % 2 == 0
        ws3.cell(row=i+2, column=1, value=i+1).border = BORDER
        kw_c = concepts_c[i] if i < len(concepts_c) else {}
        kw_d = concepts_d[i] if i < len(concepts_d) else {}
        uniq  = unique_scibert[i] if i < len(unique_scibert) else {}
        dat(ws3.cell(row=i+2, column=2), kw_c.get("text",""), alt=alt)
        dat(ws3.cell(row=i+2, column=3), kw_c.get("score",""), alt=alt)
        dat(ws3.cell(row=i+2, column=4), kw_d.get("text",""), scibert=True)
        dat(ws3.cell(row=i+2, column=5), kw_d.get("score",""), scibert=True)
        dat(ws3.cell(row=i+2, column=6), uniq.get("text",""), scibert=True)

    for ci, w in enumerate([5,32,10,32,10,32], 1):
        ws3.column_dimensions[get_column_letter(ci)].width = w

    # ── Sheet 4: NER Entity Types ────────────────────────────────────────────────
    ws4 = wb.create_sheet("NER Entity Types")
    ws4.sheet_view.showGridLines = False

    all_labels = sorted(set(
        list(results["spacy_en_core_web_sm"].get("entity_types",{}).keys()) +
        list(results["scispacy_en_core_sci_sm"].get("entity_types",{}).keys())
    ))
    for c, h in enumerate(["Entity Type","spaCy en_core_web_sm","SciSpacy en_core_sci_sm"], 1):
        hdr(ws4.cell(row=1, column=c), h)
    for ri, label in enumerate(all_labels, 2):
        alt = ri % 2 == 0
        fld(ws4.cell(row=ri, column=1), label)
        dat(ws4.cell(row=ri, column=2), results["spacy_en_core_web_sm"]["entity_types"].get(label,0), alt=alt)
        dat(ws4.cell(row=ri, column=3), results["scispacy_en_core_sci_sm"]["entity_types"].get(label,0), alt=alt, scibert=True)
    for ci, w in enumerate([22,26,28], 1):
        ws4.column_dimensions[get_column_letter(ci)].width = w

    # ── Sheet 5: Overlap Analysis ────────────────────────────────────────────────
    ws5 = wb.create_sheet("Overlap Analysis")
    ws5.sheet_view.showGridLines = False
    ov = results.get("_overlap", {})

    for c, h in enumerate(["Comparison","Value"], 1):
        hdr(ws5.cell(row=1, column=c), h)

    overlap_rows = [
        ("NER: shared (spaCy ∩ SciSpacy)",        ov.get("ner_shared",0)),
        ("NER: only in spaCy",                     ov.get("ner_only_spacy",0)),
        ("NER: only in SciSpacy",                  ov.get("ner_only_scispacy",0)),
        ("Keyphrases: shared (bge ∩ SciBERT)",     ov.get("kp_shared",0)),
        ("Keyphrases: only in bge-small",           ov.get("kp_only_bge",0)),
        ("Keyphrases: only in SciBERT",             ov.get("kp_only_scibert",0)),
        ("Unique to SciBERT (sample)",              ", ".join(ov.get("kp_unique_scibert_sample",[])[:10])),
        ("Unique to SciSpacy (sample)",             ", ".join(ov.get("ner_unique_scispacy_sample",[])[:10])),
    ]
    for ri, (label, val) in enumerate(overlap_rows, 2):
        fld(ws5.cell(row=ri, column=1), label)
        sci = "SciBERT" in label or "SciSpacy" in label
        dat(ws5.cell(row=ri, column=2), val, scibert=sci)
        ws5.row_dimensions[ri].height = 30

    ws5.column_dimensions["A"].width = 40
    ws5.column_dimensions["B"].width = 60

    wb.save(XLSX_PATH)
    print(f"📊 Excel saved → {XLSX_PATH}")
    import subprocess
    subprocess.Popen(["open", str(XLSX_PATH)])


if __name__ == "__main__":
    main()
