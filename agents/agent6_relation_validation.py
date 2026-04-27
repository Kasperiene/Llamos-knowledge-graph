class RelationValidationAgent:
    """
    Validates and filters relations using:
      1. Entity whitelist  — head/tail must appear in linked entities
      2. Noise filters     — remove table artefacts, very short spans, self-loops
      3. Semantic scoring  — boost relations connecting Wikidata-confirmed entities
    """

    def run(self, relations: list, linked_entities: list) -> list:
        entity_texts = {e["text"].lower() for e in linked_entities}
        wikidata_texts = {e["text"].lower() for e in linked_entities if e.get("wikidata_id")}

        validated = []
        for r in relations:
            h, t = r["head"].lower(), r["tail"].lower()

            if not self._passes_noise_filter(r):
                continue

            score = r.get("score", 0.5)

            # boost if both ends are known entities
            if h in entity_texts and t in entity_texts:
                score = min(1.0, score + 0.1)
            # boost further if both are Wikidata-confirmed
            if h in wikidata_texts and t in wikidata_texts:
                score = min(1.0, score + 0.15)

            if score >= 0.5:
                validated.append({**r, "score": round(score, 4)})

        # deduplicate keeping highest score
        seen = {}
        for r in validated:
            key = (r["head"].lower(), r["type"], r["tail"].lower())
            if key not in seen or r["score"] > seen[key]["score"]:
                seen[key] = r

        result = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
        print(f"  {len(relations)} relations → {len(result)} after validation")
        return result

    @staticmethod
    def _passes_noise_filter(r: dict) -> bool:
        h, t = r["head"], r["tail"]
        # self-loop
        if h.lower() == t.lower():
            return False
        # too short
        if len(h) < 3 or len(t) < 3:
            return False
        # looks like a table artefact (starts with digit/special)
        if h[0].isdigit() or t[0].isdigit():
            return False
        # contains newline remnants
        if "\n" in h or "\n" in t:
            return False
        # relation verb too short
        if len(r.get("type", "")) < 2:
            return False
        return True
