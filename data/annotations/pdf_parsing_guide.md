# PDF Parsing Evaluation Guide v1.0

## Scope

This guide covers how to evaluate **PDF parsing quality** — the step that converts PDF bytes into machine-readable text. It covers only what the *parser* produces. Errors made by downstream NLP or LLM components are **not** recorded here; use the research annotation schema for those.

---

## Core distinction: parsing error vs. interpretation error

| Type | Definition | Belongs here? |
|------|-----------|---------------|
| **Parsing error** | Parser produces wrong/missing text from the PDF. The original information was in the PDF; the parser failed to extract it correctly. | Yes |
| **Interpretation error** | Parser text is correct, but a downstream model (LLM, NLP pipeline) misunderstood it. | No — record in LLM extraction evaluation |

**Examples:**

| Situation | Type | Record here? |
|-----------|------|-------------|
| OCR reads "β" as "b" | parsing_error | Yes |
| Column 2 text appears before column 1 | parsing_error | Yes |
| Table cells merged into a single string | parsing_error | Yes |
| "N = 213" correctly extracted but LLM reports N=231 | interpretation_error | No |
| Abstract correctly extracted but LLM classifies it as a finding | interpretation_error | No |

---

## Error categories

| Category | What to look for |
|----------|-----------------|
| `text_accuracy` | Characters wrong: OCR errors, encoding issues, ligatures broken, Greek letters replaced (α→a, β→b, ≥ dropped) |
| `text_completeness` | Sentences, paragraphs, or whole sections silently dropped |
| `reading_order` | Multi-column layout merged incorrectly; figures/tables interleaved with main text; footnote text appearing mid-sentence |
| `section_structure` | Section headings missing, merged with body text, or incorrectly split into sub-headings |
| `metadata` | Title, author list, year, DOI, journal name wrong or missing |
| `tables` | Cell values swapped, rows merged, header row merged with data, numeric values garbled |
| `footnotes` | Footnote content merged into body paragraph; footnote marker (superscript) dropped |
| `references` | Reference list truncated, entries merged, author names garbled, DOIs broken |
| `scientific_content_substitution` | Formulae, equations, or statistical notation replaced with wrong text (e.g. χ²→x2, *p*→p, subscripts/superscripts dropped) |

---

## Severity guide

| Severity | Decision rule | Example |
|----------|--------------|---------|
| `critical` | Makes a key fact unrecoverable or completely wrong for any reader of the output | Sample size "N=213" extracted as "N=21"; hypothesis dropped entirely |
| `major` | Affects a meaningful unit (paragraph, table, section heading); likely to cause downstream errors | Entire Method section missing; table body garbled |
| `minor` | Affects one sentence or a non-essential element; recoverable from context | One citation garbled in reference list; minor OCR error in surname |
| `cosmetic` | Formatting/whitespace only; content fully preserved | Extra blank line between paragraphs; bold markers not stripped |

---

## How to evaluate a parser run

1. Open the source PDF and the parser's text output side by side.
2. Read through the full output systematically. Check these sections explicitly:
   - Title page / header (metadata)
   - Abstract
   - Method / Participants (sample info, constructs, instruments)
   - Results (statistics, hypotheses tested)
   - Tables
   - References / bibliography
3. For each error, record:
   - `original_content`: exact text from PDF (copy-paste or transcribe)
   - `system_output`: exact text the parser produced
   - `source_location.page`: page in the PDF (not the parser's output page count)
   - `source_location.section`: section heading in the PDF
4. Do NOT infer what the parser "probably meant." If you are unsure whether a difference is an error, record it as `minor` with a comment.

---

## File structure

All runs are stored in a single `pdf_parsing_errors.json` file with:
```json
{
  "schema_version": "1.0",
  "runs": [
    {
      "run_id": "mineru_steffens_2014_run1",
      "paper_id": "Steffens et al. - 2014 - Leadership as social identity management Introduc",
      "pdf_path": "data/papers/pilot_10/Steffens et al. - 2014 - ...",
      "pdf_sha256": "<hash>",
      "parser_system": "MinerU",
      "parser_version": "1.2.0",
      "configuration": { "device": "cpu", "model": "layoutreader" },
      "run_date": "2026-10-11",
      "annotator": "Rimante Kasperiene",
      "errors": [
        {
          "error_id": "E001",
          "category": "metadata",
          "error_type": "parsing_error",
          "severity": "major",
          "source_location": { "page": 1, "region": "header", "section": null, "bounding_box": null },
          "original_content": "Steffens, N. J., Haslam, S. A., Reicher, S. D., Platow, M. J., ...",
          "system_output": "Steffens N J Haslam S A Reicher S D Platow M J",
          "annotator": "Rimante Kasperiene",
          "comment": "Author list extracted without commas; first names reduced to initials only."
        }
      ],
      "summary_notes": "MinerU correctly extracts body text but loses author name formatting on title page."
    }
  ]
}
```

---

## Pilot paper selection rationale (layout diversity)

The 10 pilot papers were selected to cover diverse PDF layouts, not only MRQ 2025 membership:

| Paper | Layout feature tested |
|-------|----------------------|
| Alvesson 2020 | Accepted manuscript (non-typeset, Warwick WRAP) |
| Butalia 2024 | Scale validation with psychometric tables |
| Fransen 2022 | Longitudinal tables with multiple time points |
| Frenzel 2022 | Multi-country data tables |
| Gill 2015 | Qualitative — dense narrative, no tables |
| Haslam 2023 | RCT CONSORT flow diagram |
| Haslam et al. 2022 | Political science cross-cultural survey |
| Roodt 2021 | Mediation model diagrams |
| Steffens 2014 | Two-column journal layout, multi-study |
| VanDick 2021 | SEM path model |

MRQ 2025 membership is tracked in `pilot_manifest.json` but is not a selection criterion for parsing evaluation.

---

## What NOT to record

- Parser speed or memory usage (separate benchmark)
- Rendering issues in a PDF viewer
- Stylistic differences (e.g. parser uses spaces where PDF has non-breaking space)
- Anything that requires understanding the paper's content (that is interpretation, not parsing)
