from pathlib import Path


class GraphEnrichmentAgent:
    """
    Enriches the knowledge graph with:
      - PageRank — most influential nodes
      - Degree centrality — most connected nodes
      - Community detection (Louvain)
      - Basic link prediction (Jaccard coefficient)
    Saves enrichment report to data/output/enrichment_report.json
    """

    OUTPUT_DIR = Path("data/output")

    def run(self, graph) -> None:
        import networkx as nx
        import json

        if graph.number_of_nodes() == 0:
            print("  Graph is empty — skipping enrichment")
            return

        # convert to undirected for community detection
        ug = graph.to_undirected()

        print("  Computing PageRank...")
        pagerank = nx.pagerank(graph, alpha=0.85)

        print("  Computing degree centrality...")
        degree = dict(nx.degree_centrality(graph))

        print("  Detecting communities...")
        communities = self._detect_communities(ug)

        print("  Predicting links...")
        predicted_links = self._predict_links(ug)

        top_nodes = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:20]
        top_labels = [graph.nodes[n].get("label", n.split("/")[-1]) for n, _ in top_nodes]

        report = {
            "stats": {
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "communities": len(communities),
                "density": round(nx.density(graph), 6),
            },
            "top_nodes_by_pagerank": [
                {"label": graph.nodes[n].get("label", n), "score": round(s, 6)}
                for n, s in top_nodes
            ],
            "communities": [
                {"id": i, "size": len(c), "members": [
                    graph.nodes[n].get("label", n) for n in list(c)[:5]
                ]}
                for i, c in enumerate(communities[:10])
            ],
            "predicted_links": [
                {"from": graph.nodes.get(u, {}).get("label", u),
                 "to": graph.nodes.get(v, {}).get("label", v),
                 "score": round(s, 4)}
                for u, v, s in predicted_links[:10]
            ],
        }

        out_path = self.OUTPUT_DIR / "enrichment_report.json"
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"  Communities found: {len(communities)}")
        print(f"  Top node: {top_labels[0] if top_labels else 'N/A'}")
        print(f"  Saved: {out_path}")
        return report

    @staticmethod
    def _detect_communities(ug) -> list:
        try:
            from community import best_partition
            partition = best_partition(ug)
            groups = {}
            for node, cid in partition.items():
                groups.setdefault(cid, set()).add(node)
            return sorted(groups.values(), key=len, reverse=True)
        except ImportError:
            import networkx.algorithms.community as nxcom
            try:
                comms = list(nxcom.greedy_modularity_communities(ug))
                return sorted(comms, key=len, reverse=True)
            except Exception:
                return [set(ug.nodes())]

    @staticmethod
    def _predict_links(ug) -> list:
        import networkx as nx
        try:
            preds = list(nx.jaccard_coefficient(ug))
            return sorted(preds, key=lambda x: x[2], reverse=True)
        except Exception:
            return []
