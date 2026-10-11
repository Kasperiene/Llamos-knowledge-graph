"""
Knowledge Graph Construction Pipeline
Runs all 9 agents sequentially, passing output from one to the next.
"""

from pathlib import Path
from agents.agent1_ingestion import DataIngestionAgent
from agents.agent2_embedding import SemanticEmbeddingAgent
from agents.agent3_concept_extraction import ConceptExtractionAgent
from agents.agent4_relation_extraction import RelationExtractionAgent
from agents.agent5_entity_linking import EntityLinkingAgent
from agents.agent6_relation_validation import RelationValidationAgent
from agents.agent7_ontology_builder import OntologyBuilderAgent
from agents.agent8_kg_construction import KGConstructionAgent
from agents.agent9_graph_enrichment import GraphEnrichmentAgent


def run_pipeline(input_path: str):
    print(f"\n=== Knowledge Graph Pipeline ===\n")

    # 1. Data Ingestion
    print("[1/9] Data Ingestion Agent...")
    doc = DataIngestionAgent().run(input_path)
    text = doc["text"]
    print(f"      title: {doc['title']}")
    print(f"      sections: {len(doc['sections'])}  |  references: {len(doc['references'])}")

    # 2. Semantic Embedding
    print("[2/9] Semantic Embedding Agent...")
    embeddings = SemanticEmbeddingAgent().run(text)

    # 3. Concept Extraction
    print("[3/9] Concept Extraction Agent...")
    concepts = ConceptExtractionAgent().run(text)

    # 4. Relation Extraction
    print("[4/9] Relation Extraction Agent...")
    relations = RelationExtractionAgent().run(text, concepts)

    # 5. Entity Linking (canonization + Wikidata)
    print("[5/9] Entity Linking Agent...")
    paper_id = doc.get("title") or Path(input_path).stem
    linked_entities = EntityLinkingAgent().run(concepts, paper_id=paper_id)

    # 6. Relation Validation
    print("[6/9] Relation Validation Agent...")
    validated_relations = RelationValidationAgent().run(relations, linked_entities)

    # 7. Ontology Builder
    print("[7/9] Ontology Builder Agent...")
    ontology = OntologyBuilderAgent().run(linked_entities, validated_relations)

    # 8. Knowledge Graph Construction
    print("[8/9] KG Construction Agent...")
    graph = KGConstructionAgent().run(ontology)

    # 9. Graph Enrichment
    print("[9/9] Graph Enrichment Agent...")
    GraphEnrichmentAgent().run(graph)

    print("\n=== Pipeline complete ===\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python main.py <path_to_document>")
        sys.exit(1)
    run_pipeline(sys.argv[1])
