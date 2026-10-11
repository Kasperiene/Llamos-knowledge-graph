import re
import time
import requests
from difflib import SequenceMatcher


# ─────────────────────────────────────────── normalisation ───────────────────

# Domain abbreviations common in the identity leadership corpus
_ABBREV = {
    r"\bIL\b":    "identity leadership",
    r"\bSIL\b":   "social identity leadership",
    r"\bSIT\b":   "social identity theory",
    r"\bSCT\b":   "self-categorization theory",
    r"\bHR\b":    "human resources",
    r"\bORGs?\b": "organization",
    r"\bWE\b":    "work engagement",
}


def normalize(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = t.replace("'s", "").replace("’s", "")
    for pat, repl in _ABBREV.items():
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    return t.strip()


def _similar(a: str, b: str, threshold: float = 0.85) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold


# ─────────────────────────────────────────── concept registry ────────────────

class ConceptRegistry:
    """
    Canonical concept store — can be shared across multiple papers (batch mode)
    or used for within-document deduplication (single-PDF mode).

    Merges near-duplicates via exact → alias → fuzzy matching after normalisation.
    """

    def __init__(self):
        self._canon: dict[str, dict] = {}  # norm_key → entry
        self._alias: dict[str, str] = {}   # variant → canon_key

    def add(self, concept: dict, paper_id: str) -> str:
        raw  = concept["text"]
        norm = normalize(raw)

        # 1. exact match
        if norm in self._canon:
            e = self._canon[norm]
            e["frequency"] += concept.get("frequency", 1)
            e["papers"].add(paper_id)
            if concept.get("score", 0) > e["best_score"]:
                e["best_score"] = concept["score"]
                e["display_text"] = raw
            return norm

        # 2. alias lookup
        if norm in self._alias:
            canon_key = self._alias[norm]
            return self.add({**concept, "text": self._canon[canon_key]["display_text"]}, paper_id)

        # 3. fuzzy match (only check entries of similar length)
        for ek in self._canon:
            if abs(len(norm) - len(ek)) > 6:
                continue
            if _similar(norm, ek):
                self._alias[norm] = ek
                return self.add({**concept, "text": self._canon[ek]["display_text"]}, paper_id)

        # 4. new entry
        self._canon[norm] = {
            "display_text": raw,
            "norm_key":     norm,
            "type":         concept.get("type", "KEYWORD"),
            "label":        concept.get("label"),
            "frequency":    concept.get("frequency", 1),
            "best_score":   concept.get("score", 0.0),
            "papers":       {paper_id},
        }
        return norm

    def concepts(self) -> list[dict]:
        return [
            {**v, "papers": sorted(v["papers"]), "paper_count": len(v["papers"])}
            for v in self._canon.values()
        ]

    def canon_keys(self) -> set[str]:
        return set(self._canon.keys())


# ─────────────────────────────────────────── agent ───────────────────────────

class EntityLinkingAgent:
    """
    Two-step agent:
      1. Canonization  — normalises and deduplicates concepts via ConceptRegistry.
      2. Entity linking — links ENTITY-type concepts to Wikidata (optional).

    Single-PDF usage:
        agent5 = EntityLinkingAgent()
        linked = agent5.run(concepts, paper_id="paper_1")

    Batch usage (shared registry across papers, no Wikidata):
        registry = ConceptRegistry()
        agent5   = EntityLinkingAgent(registry=registry, link_wikidata=False)
        for paper in papers:
            canon = agent5.canonize(paper["concepts"], paper_id=paper["id"])
        all_concepts = registry.concepts()
    """

    WIKIDATA_URL = "https://www.wikidata.org/w/api.php"
    DELAY = 0.15

    def __init__(self, registry: ConceptRegistry | None = None,
                 link_wikidata: bool = True):
        self.registry      = registry or ConceptRegistry()
        self.link_wikidata = link_wikidata

    # ── Step 1: canonization ──────────────────────────────────────────────────

    def canonize(self, concepts: list, paper_id: str) -> list:
        """
        Normalise and deduplicate concepts against the shared registry.
        Returns the same list with two extra fields per concept:
          - norm_key:  normalised canonical key (used as graph node ID)
          - canonical: best display text for this concept across all papers
        """
        result = []
        for c in concepts:
            norm_key = self.registry.add(c, paper_id)
            result.append({
                **c,
                "norm_key":  norm_key,
                "canonical": self.registry._canon[norm_key]["display_text"],
            })
        return result

    # ── Step 2: Wikidata linking ──────────────────────────────────────────────

    def run(self, concepts: list, paper_id: str = "default") -> list:
        """Canonize, then optionally link ENTITY-type concepts to Wikidata."""
        canon = self.canonize(concepts, paper_id)

        if not self.link_wikidata:
            return canon

        entities = [c for c in canon if c.get("type") == "ENTITY"]
        others   = [c for c in canon if c.get("type") != "ENTITY"]

        print(f"  Linking {len(entities)} entities to Wikidata...")
        linked = []
        for i, entity in enumerate(entities):
            wd = self._link(entity["canonical"])
            entry = {**entity, "wikidata_id": None, "wikidata_label": None,
                     "wikidata_desc": None, "wikidata_url": None}
            if wd:
                entry.update({
                    "wikidata_id":    wd["id"],
                    "wikidata_label": wd["label"],
                    "wikidata_desc":  wd.get("description", ""),
                    "wikidata_url":   f"https://www.wikidata.org/wiki/{wd['id']}",
                })
            linked.append(entry)
            time.sleep(self.DELAY)
            if (i + 1) % 20 == 0:
                print(f"    {i + 1}/{len(entities)} linked...")

        matched = sum(1 for e in linked if e["wikidata_id"])
        print(f"  Linked {matched}/{len(entities)} entities to Wikidata")
        return linked + others

    def _link(self, text: str) -> dict | None:
        try:
            r = requests.get(self.WIKIDATA_URL, params={
                "action":   "wbsearchentities",
                "search":   text,
                "language": "en",
                "format":   "json",
                "limit":    1,
            }, headers={"User-Agent": "LlamosKG/1.0 (knowledge-graph-pipeline; kasperiene@gmail.com)"},
               timeout=10)
            r.raise_for_status()
            results = r.json().get("search", [])
            if results:
                return results[0]
        except Exception:
            pass
        return None
