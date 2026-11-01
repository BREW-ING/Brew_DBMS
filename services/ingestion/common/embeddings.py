"""Text embeddings via fastembed (ONNX, CPU; no torch).

The model is the same one the web app's vectors must come from:
sentence-transformers/all-MiniLM-L6-v2, 384 dims (problem_signals.embedding is
vector(384)). It is downloaded on first use and loaded once per process.
"""

from functools import lru_cache

from fastembed import TextEmbedding

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
DEFAULT_BATCH_SIZE = 64


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=MODEL_NAME)


def embed_texts(texts: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[float]]:
    """Embed `texts` in batches; returns one 384-float vector per input, in order."""
    if not texts:
        return []
    vectors = [v.tolist() for v in _model().embed(texts, batch_size=batch_size)]
    if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIM for v in vectors):
        raise RuntimeError(f"{MODEL_NAME} returned unexpected output shape")
    return vectors


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
