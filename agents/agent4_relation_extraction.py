class RelationExtractionAgent:
    """
    Extracts (head, relation, tail) triples using two methods:
      1. spaCy dependency parsing — SVO triples (fast, no extra download)
      2. REBEL model            — deep relation extraction (optional, ~1.4 GB)
    Default: spaCy SVO only. Pass use_rebel=True to enable REBEL.
    """

    def __init__(self, spacy_model: str = "en_core_web_sm", use_rebel: bool = False):
        self.spacy_model = spacy_model
        self.use_rebel = use_rebel
        self._nlp = None
        self._rebel = None

    def run(self, text: str, concepts: list) -> list:
        concept_set = {c["text"].lower() for c in concepts}
        relations = []

        print("  [4a] spaCy SVO extraction...")
        relations += self._extract_svo(text)

        if self.use_rebel:
            print("  [4b] REBEL relation extraction...")
            relations += self._extract_rebel(text)

        filtered = self._filter(relations, concept_set)
        print(f"  Extracted {len(filtered)} relations")
        return filtered

    # ------------------------------------------------------------------ spaCy SVO

    def _extract_svo(self, text: str) -> list:
        import spacy
        if self._nlp is None:
            self._nlp = spacy.load(self.spacy_model)

        triples = []
        chunk_size = 50_000
        for i in range(0, len(text), chunk_size):
            doc = self._nlp(text[i:i + chunk_size])
            for sent in doc.sents:
                triples += self._svo_from_sent(sent)
        return triples

    @staticmethod
    def _svo_from_sent(sent) -> list:
        triples = []
        for token in sent:
            if token.dep_ in ("nsubj", "nsubjpass") and token.head.pos_ == "VERB":
                subject = RelationExtractionAgent._get_span(token)
                verb = token.head.lemma_.lower()
                for child in token.head.children:
                    if child.dep_ in ("dobj", "attr", "acomp", "pobj"):
                        obj = RelationExtractionAgent._get_span(child)
                        if subject and obj and subject.lower() != obj.lower():
                            triples.append({
                                "head": subject,
                                "type": verb,
                                "tail": obj,
                                "source": "svo",
                                "score": 0.75,
                            })
        return triples

    # pronouns, determiners, and generic words that are never meaningful entities
    _BLOCKLIST = {
        "i", "me", "my", "we", "us", "our", "you", "your", "he", "him", "his",
        "she", "her", "it", "its", "they", "them", "their", "this", "that",
        "these", "those", "which", "who", "what", "there", "here", "where",
        "when", "how", "why", "all", "both", "each", "few", "more", "most",
        "other", "some", "such", "no", "nor", "not", "only", "own", "same",
        "than", "too", "very", "just", "one", "two", "also", "so", "yet",
        "place", "way", "time", "part", "role", "use", "number", "level",
        "case", "fact", "point", "thing", "kind", "type", "example", "result",
        "access", "attention", "focus", "need", "ability", "order",
    }

    @staticmethod
    def _get_span(token) -> str:
        # reject pronouns, determiners, and stop words immediately
        if token.pos_ in ("PRON", "DET") or token.is_stop:
            return ""
        if token.text.lower() in RelationExtractionAgent._BLOCKLIST:
            return ""
        parts = [token.text]
        for child in token.lefts:
            if child.dep_ in ("compound", "amod", "nn") and not child.is_stop:
                parts.insert(0, child.text)
        for child in token.rights:
            if child.dep_ in ("compound", "nn") and not child.is_stop:
                parts.append(child.text)
        return " ".join(parts).strip()

    # ------------------------------------------------------------------ REBEL

    def _extract_rebel(self, text: str) -> list:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        if self._rebel is None:
            name = "Babelscape/rebel-large"
            print(f"    Loading {name}...")
            tok = AutoTokenizer.from_pretrained(name)
            mdl = AutoModelForSeq2SeqLM.from_pretrained(name)
            self._rebel = (tok, mdl)

        tokenizer, model = self._rebel
        triples = []
        chunk_size = 512
        words = text.split()
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            inputs = tokenizer(chunk, return_tensors="pt",
                               truncation=True, max_length=512)
            outputs = model.generate(**inputs, max_length=512)
            decoded = tokenizer.batch_decode(outputs, skip_special_tokens=False)[0]
            triples += self._parse_rebel(decoded)
        return triples

    @staticmethod
    def _parse_rebel(text: str) -> list:
        triples = []
        subject = relation = obj = ""
        current = "x"
        for token in text.replace("<s>", "").replace("</s>", "").replace("<pad>", "").split():
            if token == "<triplet>":
                if subject and relation and obj:
                    triples.append({"head": subject.strip(), "type": relation.strip(),
                                    "tail": obj.strip(), "source": "rebel", "score": 0.9})
                subject = relation = obj = ""
                current = "t"
            elif token == "<subj>":
                current = "s"
                obj = ""
            elif token == "<obj>":
                current = "o"
                relation = ""
            else:
                if current == "t":
                    subject += " " + token
                elif current == "s":
                    obj += " " + token
                elif current == "o":
                    relation += " " + token
        if subject and relation and obj:
            triples.append({"head": subject.strip(), "type": relation.strip(),
                            "tail": obj.strip(), "source": "rebel", "score": 0.9})
        return triples

    # ------------------------------------------------------------------ filter

    @staticmethod
    def _filter(relations: list, concept_set: set) -> list:
        seen, out = set(), []
        for r in relations:
            h, t = r["head"].strip(), r["tail"].strip()
            if not h or not t:
                continue
            if len(h) > 80 or len(t) > 80:
                continue
            # single-word nodes must be capitalised (proper noun) or in concept set
            if " " not in h and not h[0].isupper() and h.lower() not in concept_set:
                continue
            if " " not in t and not t[0].isupper() and t.lower() not in concept_set:
                continue
            if h.lower() in RelationExtractionAgent._BLOCKLIST:
                continue
            if t.lower() in RelationExtractionAgent._BLOCKLIST:
                continue
            key = (h.lower(), r["type"], t.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({**r, "head": h, "tail": t})
        return out
