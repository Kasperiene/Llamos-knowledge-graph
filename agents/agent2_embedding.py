import re


class SemanticEmbeddingAgent:
    """
    Splits text into overlapping chunks and generates sentence embeddings.
    Default model: BAAI/bge-small-en-v1.5 (free, top MTEB benchmark score).
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5",
                 chunk_size: int = 512, overlap: int = 64):
        self.model_name = model_name
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            print(f"  Loading model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def run(self, text: str) -> dict:
        chunks = self._chunk_text(text)
        model = self._load_model()

        print(f"  Encoding {len(chunks)} chunks...")
        embeddings = model.encode(chunks, show_progress_bar=True,
                                  normalize_embeddings=True)

        return {
            "model": self.model_name,
            "dim": embeddings.shape[1],
            "chunks": chunks,
            "embeddings": embeddings.tolist(),
        }

    # ------------------------------------------------------------------ chunking

    def _chunk_text(self, text: str) -> list:
        sentences = self._split_sentences(text)
        chunks = []
        current, current_len = [], 0

        for sentence in sentences:
            s_len = len(sentence)

            if current_len + s_len > self.chunk_size and current:
                chunks.append(" ".join(current))
                # keep overlap: drop sentences from front until under overlap size
                while current and current_len > self.overlap:
                    removed = current.pop(0)
                    current_len -= len(removed)

            current.append(sentence)
            current_len += s_len

        if current:
            chunks.append(" ".join(current))

        return [c for c in chunks if c.strip()]

    @staticmethod
    def _split_sentences(text: str) -> list:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
