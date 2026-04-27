from pathlib import Path


class KGConstructionAgent:
    """
    Builds a NetworkX graph from the RDF ontology and persists it to:
      - data/output/knowledge_graph.graphml
      - data/output/knowledge_graph.ttl  (RDF Turtle)
      - data/output/knowledge_graph.json (node-link format)
    """

    OUTPUT_DIR = Path("data/output")

    def run(self, ontology) -> object:
        import networkx as nx
        from rdflib import RDF, RDFS, OWL, URIRef, Literal

        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        g = nx.MultiDiGraph()

        OWL_OP = OWL.ObjectProperty
        for s, p, o in ontology:
            # only add triples that are object-property assertions
            if (p, RDF.type, OWL_OP) in ontology:
                s_label = self._label(ontology, s)
                o_label = self._label(ontology, o)
                p_label = self._label(ontology, p)
                g.add_node(str(s), label=s_label)
                g.add_node(str(o), label=o_label)
                g.add_edge(str(s), str(o), relation=p_label)

        # sanitize node labels for XML compatibility
        import re
        for node in g.nodes:
            lbl = g.nodes[node].get("label", "")
            g.nodes[node]["label"] = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", lbl)
        for u, v, data in g.edges(data=True):
            rel = data.get("relation", "")
            data["relation"] = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", rel)

        # save outputs
        ttl_path = self.OUTPUT_DIR / "knowledge_graph.ttl"
        ontology.serialize(destination=str(ttl_path), format="turtle")

        graphml_path = self.OUTPUT_DIR / "knowledge_graph.graphml"
        nx.write_graphml(g, str(graphml_path))

        import json
        json_path = self.OUTPUT_DIR / "knowledge_graph.json"
        data = nx.node_link_data(g)
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"  Graph: {g.number_of_nodes()} nodes | {g.number_of_edges()} edges")
        print(f"  Saved: {ttl_path}")
        print(f"  Saved: {graphml_path}")
        print(f"  Saved: {json_path}")
        return g

    @staticmethod
    def _label(graph, uri) -> str:
        from rdflib import RDFS, Literal
        for _, _, label in graph.triples((uri, RDFS.label, None)):
            return str(label)
        return str(uri).split("/")[-1].replace("_", " ")
