import re
from collections import Counter


class ConceptExtractionAgent:
    """
    Extracts concepts from text using three complementary methods:
      1. spaCy NER       — named entities (ORG, PERSON, GPE, EVENT, ...)
      2. KeyBERT         — semantic keyphrases via embedding similarity
      3. YAKE            — statistical keyword extraction (no model required)
    Results are merged, deduplicated, and ranked by frequency + score.
    """

    def __init__(self,
                 spacy_model: str = "en_core_web_sm",
                 embedding_model: str = "BAAI/bge-small-en-v1.5",
                 top_n_keybert: int = 30,
                 top_n_yake: int = 30):
        self.spacy_model = spacy_model
        self.embedding_model = embedding_model
        self.top_n_keybert = top_n_keybert
        self.top_n_yake = top_n_yake
        self._nlp = None
        self._kw_model = None

    # ------------------------------------------------------------------ public

    def run(self, text: str) -> list:
        concepts = []

        print("  [3a] spaCy NER...")
        concepts += self._extract_entities(text)

        print("  [3b] KeyBERT keyphrases...")
        concepts += self._extract_keybert(text)

        print("  [3c] YAKE keywords...")
        concepts += self._extract_yake(text)

        merged = self._merge(concepts, text)
        print(f"  Extracted {len(merged)} unique concepts")
        return merged

    # ------------------------------------------------------------------ extractors

    def _extract_entities(self, text: str) -> list:
        import spacy
        if self._nlp is None:
            try:
                self._nlp = spacy.load(self.spacy_model)
            except OSError:
                import subprocess, sys
                subprocess.run([sys.executable, "-m", "spacy", "download", self.spacy_model], check=True)
                self._nlp = spacy.load(self.spacy_model)

        # spaCy has a max doc length — process in chunks
        chunk_size = 100_000
        results = []
        for i in range(0, len(text), chunk_size):
            doc = self._nlp(text[i:i + chunk_size])
            for ent in doc.ents:
                if ent.label_ in {"ORG", "PERSON", "GPE", "LOC", "EVENT",
                                   "PRODUCT", "LAW", "NORP", "FAC", "WORK_OF_ART"}:
                    results.append({
                        "text": ent.text.strip(),
                        "type": "ENTITY",
                        "label": ent.label_,
                        "score": 1.0,
                    })
        return results

    def _extract_keybert(self, text: str) -> list:
        from keybert import KeyBERT
        if self._kw_model is None:
            self._kw_model = KeyBERT(model=self.embedding_model)

        # KeyBERT works best on smaller text — use first 10k chars
        sample = text[:10_000]
        keywords = self._kw_model.extract_keywords(
            sample,
            keyphrase_ngram_range=(1, 3),
            stop_words="english",
            use_mmr=True,       # diversity via Maximal Marginal Relevance
            diversity=0.5,
            top_n=self.top_n_keybert,
        )
        return [{"text": kw, "type": "KEYPHRASE", "label": None, "score": score}
                for kw, score in keywords]

    def _extract_yake(self, text: str) -> list:
        import yake
        extractor = yake.KeywordExtractor(
            lan="en", n=3, dedupLim=0.7,
            top=self.top_n_yake, features=None
        )
        keywords = extractor.extract_keywords(text)
        # YAKE scores are inverse — lower is better; normalise to 0-1
        if keywords:
            max_score = max(s for _, s in keywords) or 1
            return [{"text": kw, "type": "KEYWORD", "label": None,
                     "score": round(1 - (score / max_score), 4)}
                    for kw, score in keywords]
        return []

    # ------------------------------------------------------------------ merge

    def _merge(self, concepts: list, text: str) -> list:
        counts = Counter(text.lower().split())
        seen, merged = {}, []

        for c in concepts:
            key = c["text"].lower().strip()
            # skip noise: single chars, numbers only, very long strings
            if len(key) < 3 or key.isdigit() or len(key) > 80:
                continue
            key = re.sub(r"\s+", " ", key)

            freq = sum(counts.get(w, 0) for w in key.split())

            if key in seen:
                existing = seen[key]
                existing["score"] = max(existing["score"], c["score"])
                existing["frequency"] = freq
                if c["label"] and not existing["label"]:
                    existing["label"] = c["label"]
            else:
                entry = {**c, "text": c["text"].strip(), "frequency": freq}
                seen[key] = entry
                merged.append(entry)

        # rank: entity type first, then score × log(frequency+1)
        import math
        merged.sort(
            key=lambda x: (x["type"] == "ENTITY", x["score"] * math.log(x["frequency"] + 2)),
            reverse=True,
        )
        return merged
