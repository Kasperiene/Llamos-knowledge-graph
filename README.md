# Llamos-knowledge-graph

## Pipeline

- **Paper Reader Agent**
- **Concept Extraction (SciBERT)**
- **Relation Extraction (REBEL)**
- **LLM Validation**
- **RDF Ontology Builder**
- **Neo4j Knowledge Graph**

---

## Populiariausi agent framework

### Nemokami
- LangGraph  
- CrewAI  
- AutoGen  

### Mokami
- OpenAI Agents  
- Anthropic Agents  

---

## Naujausia metodologija (2024–2025)

- Data Ingestion Agent  
- Embedding Agent  
- Concept Extraction Agent  
- Relation Extraction Agent  
- Entity Linking Agent  
- Relation Validation Agent  
- Ontology Builder Agent  
- Knowledge Graph Construction Agent  
- Graph Enrichment Agent  

---

## Moderniausios technologijos (2025)

Svarbiausios naujovės:

1. **LLM-based extraction**  
2. **Embedding + semantic search**  
3. **Agent orchestration (LangGraph, CrewAI)**  
4. **Graph reasoning AI**

---

# Agent paaiškinimas

## Modern Knowledge Graph Construction Pipeline (2025)

---

# 1. Data Ingestion Agent

**Tikslas:** nuskaityti dokumentus ir paruošti tekstą.

### Funkcijos
- dokumentų parsisiuntimas  
- PDF / HTML / DOCX nuskaitymas  
- teksto normalizavimas  
- OCR jei dokumentas skenuotas  

### Technologijos
- document parsing  
- OCR  
- text cleaning  

### Galimi modeliai / įrankiai

**Nemokami**
- GROBID (mokslinių straipsnių parsing)  
- Apache Tika  
- PyMuPDF  
- Unstructured.io  

**Mokami**
- Google Document AI  
- AWS Textract  
- Azure Form Recognizer  

### Output
- švarus tekstas  
- struktūra (section, title, references)

---

# 2. Semantic Embedding Agent

**Tikslas:** paversti tekstą vektoriais.

Tai leidžia:

- semantinę paiešką  
- konceptų identifikavimą  
- panašumo skaičiavimą  

### Technologija
- embedding models  
- vector representation  

### Modeliai

**Nemokami**
- Sentence-BERT  
- E5 embeddings  
- Instructor embeddings  
- BGE embeddings  

**Mokami**
- OpenAI text-embedding-3-large  
- Cohere Embed  
- VoyageAI embeddings  

---

# 3. Concept Extraction Agent

**Tikslas:** identifikuoti svarbiausias sąvokas.

### Naudojami metodai

1. NER (Named Entity Recognition)  
2. Keyphrase extraction  
3. LLM extraction  

### Technologijos
- POS tagging  
- NER  
- dependency parsing  
- LLM extraction  

### Modeliai

**Nemokami**
- SpaCy transformer NER  
- Flair NER  
- SciBERT  
- KeyBERT  
- YAKE  

**Mokami**
- GPT-4 / GPT-5  
- Claude  
- Gemini  
- Cohere Command  

---

# 4. Relation Extraction Agent

**Tikslas:** nustatyti ryšius tarp sąvokų.

### Technologijos
- dependency parsing  
- semantic role labeling  
- relation classification  
- LLM reasoning  

### Modeliai

**Nemokami**
- REBEL model  
- OpenIE  
- Stanford OpenIE  
- SciIE  

**Mokami**
- GPT-4 / GPT-5 extraction  
- Claude reasoning  
- Gemini Pro  

---

# 5. Entity Linking Agent

**Tikslas:** susieti sąvokas su realiais objektais.

### Technologijos
- knowledge base linking  
- disambiguation  

### Modeliai / įrankiai

**Nemokami**
- BLINK  
- REL Entity Linker  
- DBpedia Spotlight  

**Mokami**
- Google Knowledge Graph API  
- Wikidata API enhanced services  

---

# 6. Relation Validation Agent

**Tikslas:** patikrinti ar ryšiai logiški.

### Metodai

1. ontologijos tikrinimas  
2. semantinis panašumas  
3. LLM reasoning  

### Technologijos
- ontology rules  
- semantic similarity  
- graph reasoning  

### Modeliai

**Nemokami**
- OWL reasoner  
- RDF reasoning  
- NetworkX graph validation  

**Mokami**
- LLM reasoning  
- Graph AI services  

---

# 7. Ontology Builder Agent

**Tikslas:** sukurti žinių struktūrą.

### Formatai
- RDF  
- OWL  
- property graph  

### Technologijos
- ontology engineering  
- schema generation  

### Įrankiai

**Nemokami**
- Protégé  
- RDFLib  
- OWL API  

**Mokami**
- Stardog  
- GraphDB Enterprise  

---

# 8. Knowledge Graph Construction Agent

**Tikslas:** sukurti galutinį grafą.

### Technologijos
- graph databases  
- triple stores  

### Duomenų bazės

**Nemokamos**
- Neo4j Community  
- ArangoDB  
- JanusGraph  

**Mokamos**
- Neo4j Aura  
- Amazon Neptune  
- TigerGraph  

---

# 9. Graph Enrichment Agent

**Tikslas:** papildyti grafą.

### Veiksmai
- naujų ryšių prognozė  
- graph embeddings  
- inference  

### Modeliai

**Nemokami**
- PyKEEN  
- TransE  
- ComplEx  

**Mokami**
- Graph AI cloud tools
