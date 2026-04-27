import time
import requests


class EntityLinkingAgent:
    """
    Links extracted entities to Wikidata entries (free, no API key required).
    Only links ENTITY-type concepts to avoid excessive API calls.
    """

    WIKIDATA_URL = "https://www.wikidata.org/w/api.php"
    DELAY = 0.15  # seconds between requests to respect rate limits

    def run(self, concepts: list) -> list:
        entities = [c for c in concepts if c.get("type") == "ENTITY"]
        others = [c for c in concepts if c.get("type") != "ENTITY"]

        print(f"  Linking {len(entities)} entities to Wikidata...")
        linked = []
        for i, entity in enumerate(entities):
            result = self._link(entity["text"])
            entry = {**entity, "wikidata_id": None, "wikidata_label": None,
                     "wikidata_desc": None, "wikidata_url": None}
            if result:
                entry.update({
                    "wikidata_id": result["id"],
                    "wikidata_label": result["label"],
                    "wikidata_desc": result.get("description", ""),
                    "wikidata_url": f"https://www.wikidata.org/wiki/{result['id']}",
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
                "action": "wbsearchentities",
                "search": text,
                "language": "en",
                "format": "json",
                "limit": 1,
            }, headers={"User-Agent": "LlamosKG/1.0 (knowledge-graph-pipeline; kasperiene@gmail.com)"}, timeout=10)
            r.raise_for_status()
            results = r.json().get("search", [])
            if results:
                return results[0]
        except Exception:
            pass
        return None
