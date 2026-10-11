# Annotation Guide — Identity Leadership Papers (Schema v2.0)

## Purpose

These annotations are the **human ground truth** used to evaluate LLM information extraction.
An annotation only becomes ground truth when `annotation_provenance.review_status = "verified"`.
A model-generated annotation with `review_status = "unreviewed"` is **not** a baseline.

---

## Annotation provenance — what to set

| Situation | `origin` | `review_status` |
|-----------|----------|-----------------|
| You read the PDF and fill the JSON yourself | `human` | `reviewed` → `verified` after double-check |
| A model generated it, you have not checked | `model` | `unreviewed` |
| A model generated it, you corrected it | `human_revised` | `reviewed` |
| Two annotators reconciled their versions | `final_reconciled` | `verified` |

**Rule:** A model annotation (`origin=model`) can never have `review_status=verified` by itself. A human must review it first.

Time fields:
- `human_read_time_minutes` — only wall-clock time you spent reading the PDF
- `model_run_time_seconds` — only model inference time (if applicable)
- `correction_time_minutes` — time correcting a model draft

---

## Status values for Claim fields

Every extractable fact uses a `Claim` object:

```json
{
  "value": <the extracted value>,
  "status": "reported",
  "quote": "verbatim text from paper",
  "page": 4,
  "section": "Participants",
  "fragment_id": null
}
```

| Status | Meaning | Quote required? |
|--------|---------|-----------------|
| `pending` | Not yet checked | No |
| `reported` | Explicitly stated in the paper | **Yes** (quote OR page OR section) |
| `not_reported` | You checked — it is not in the paper | No |
| `not_applicable` | Not relevant to this paper type | No |
| `ambiguous` | Present but contradictory or unclear | Yes — include the ambiguous text |

**Do not guess.** If you cannot find it, use `not_reported`. If it is irrelevant (e.g., sample size for a theoretical paper), use `not_applicable`.

---

## Paper type profiles

Set `metadata.paper_type_profile` to one of:

| Value | Description | Notes |
|-------|-------------|-------|
| `quantitative_empirical` | Survey, experiment, secondary data with statistics | Fill constructs with IV/DV roles |
| `qualitative_empirical` | Interviews, IPA, grounded theory, case study | Use role=`focal` for constructs |
| `mixed_methods` | Combines qual + quant | One study entry per method strand if appropriate |
| `scale_validation` | Psychometric development/validation | Fill `psychometric_notes` for CFA, AVE, etc. |
| `theoretical` | No data; conceptual/framework paper | `studies[]` can be empty |
| `review` | Systematic or narrative literature review | `studies[]` describes reviewed corpus, not primary data |
| `other` | Does not fit above | Explain in `notes` |

---

## Multi-study papers

Papers with Study 1, Study 2, etc. need **one entry per study** in `studies[]`.

```json
"studies": [
  { "study_id": "Study 1", "sample": { "total_n": {"value": 213, "status": "reported", ...} }, ... },
  { "study_id": "Study 2", "sample": { "total_n": {"value": 178, "status": "reported", ...} }, ... }
]
```

**Never aggregate sample sizes across studies** unless the paper itself reports a combined N.

---

## Constructs

Use `role` to describe the construct's function:

| Role | When to use |
|------|-------------|
| `independent` | Predictor/cause in a regression or experiment |
| `dependent` | Outcome variable |
| `mediator` | Tested as mediation path |
| `moderator` | Tested as interaction |
| `predictor` | Used in SEM without explicit IV/DV framing |
| `outcome` | Measured outcome without explicit DV framing |
| `focal` | Key construct in qualitative/theoretical work |
| `control` | Control variable |
| `psychometric_target` | The construct being validated (scale validation) |
| `not_applicable` | No role distinction in this paper |

---

## Hypotheses vs. results

Always distinguish:

- `item_type: "hypothesis"` — formally stated before analysis
- `item_type: "research_question"` — exploratory question, not a directional prediction
- `item_type: "exploratory"` — analysis not pre-specified
- `item_type: "post_hoc"` — analysis prompted by unexpected results

The `result` Claim should contain: `"supported"`, `"not supported"`, `"partially supported"`, or `"not tested"`.
The `effect_size` Claim should contain the reported statistic (e.g. `"β = .34, p < .001"`).

---

## Key findings

Include 3–6 findings from this paper's **own results**, not from prior literature it cites.

```json
{
  "statement": "Identity leadership predicted team performance (β = .41, p < .001).",
  "finding_type": "main_result",
  "quote": "Identity leadership was a significant predictor of team performance (β = .41, p < .001).",
  "page": 8,
  "section": "Results"
}
```

Do **not** include: claims from cited papers, general theoretical claims, or methodological descriptions.

---

## Publication version

Check the PDF header/footer. Common patterns:

- `published` — final journal version, DOI active
- `accepted_manuscript` — accepted text, not yet typeset (common in Warwick WRAP, institutional repositories)
- `postprint` — author's post-review version
- `preprint` — before peer review (e.g. PsyArXiv, arXiv)

This matters: page numbers and final wording may differ between versions.

---

## Common mistakes to avoid

1. **Do not copy from the abstract alone.** Check the Methods and Results sections directly.
2. **Do not infer IV/DV from theory** — only from the paper's own analysis description.
3. **Do not merge sample sizes** across studies.
4. **Do not use model output as ground truth** — if a model fills the annotation, mark `origin=model, review_status=unreviewed`.
5. **Do not mark a field as `reported` without a quote, page, or section.**
6. **Do not confuse prior literature claims with current paper results** in `key_findings`.
7. **Do not state a correlation as causal** unless the paper explicitly claims causality with appropriate design.

---

## Validation

Run after each session:

```bash
python tools/validate_annotations.py
```

The validator checks:
- Schema structure (required fields, enum values)
- Provenance consistency (model ≠ verified)
- Claim rules (reported → provenance present)
- Status warnings (pending fields remaining)

The output shows **structural validity and pending items** — not accuracy. Accuracy is only assessable by comparing against the PDF.
