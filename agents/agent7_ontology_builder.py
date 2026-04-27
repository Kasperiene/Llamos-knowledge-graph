class OntologyBuilderAgent:
    """
    Builds an RDF/OWL knowledge graph from validated entities and relations.
    Exports to Turtle (.ttl) format using RDFLib.
    """

    BASE_URI = "http://llamos-kg.org/"

    def run(self, linked_entities: list, validated_relations: list) -> object:
        from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef, XSD
        from rdflib.namespace import SKOS

        g = Graph()
        EX = Namespace(self.BASE_URI)
        g.bind("ex", EX)
        g.bind("owl", OWL)
        g.bind("skos", SKOS)

        # --- entity classes
        entity_labels = {e["label"] for e in linked_entities if e.get("label")}
        for label in entity_labels:
            cls = URIRef(EX + self._uri_safe(label))
            g.add((cls, RDF.type, OWL.Class))
            g.add((cls, RDFS.label, Literal(label)))

        # --- entity instances
        entity_uris = {}
        for e in linked_entities:
            uri = URIRef(EX + self._uri_safe(e["text"]))
            entity_uris[e["text"].lower()] = uri
            label = e.get("label", "Concept")
            cls = URIRef(EX + self._uri_safe(label)) if label else OWL.Thing
            g.add((uri, RDF.type, cls))
            g.add((uri, RDFS.label, Literal(e["text"])))
            if e.get("wikidata_id"):
                g.add((uri, SKOS.exactMatch,
                       URIRef(f"https://www.wikidata.org/wiki/{e['wikidata_id']}")))
            if e.get("wikidata_desc"):
                g.add((uri, RDFS.comment, Literal(e["wikidata_desc"])))

        # --- relations (object properties)
        for r in validated_relations:
            h_uri = entity_uris.get(r["head"].lower())
            t_uri = entity_uris.get(r["tail"].lower())
            if h_uri is None:
                h_uri = URIRef(EX + self._uri_safe(r["head"]))
                g.add((h_uri, RDFS.label, Literal(r["head"])))
            if t_uri is None:
                t_uri = URIRef(EX + self._uri_safe(r["tail"]))
                g.add((t_uri, RDFS.label, Literal(r["tail"])))

            prop = URIRef(EX + self._uri_safe(r["type"]))
            g.add((prop, RDF.type, OWL.ObjectProperty))
            g.add((prop, RDFS.label, Literal(r["type"])))
            g.add((h_uri, prop, t_uri))

        print(f"  Ontology: {len(g)} triples | "
              f"{len(linked_entities)} entities | {len(validated_relations)} relations")
        return g

    @staticmethod
    def _uri_safe(text: str) -> str:
        import re
        return re.sub(r"[^a-zA-Z0-9_]", "_", text.strip())[:80]
