"""Encode category documents with a local sentence-transformer (cached)."""
import numpy as np
import pandas as pd

from jeopardy import config
from jeopardy.analysis.documents import build_documents

_model = None


def get_model():
    """Lazily load and cache the SentenceTransformer (heavy import kept local)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(config.EMBED_MODEL)
    return _model


def embed_documents(documents):
    """Encode an iterable of strings into an (N, dim) float array."""
    model = get_model()
    return model.encode(
        list(documents),
        batch_size=64,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


def run_embed(force=False, limit=None):
    """Build documents, embed them, and cache the matrix + instance index."""
    if config.EMBEDDINGS_PATH.exists() and config.INSTANCES_PATH.exists() and not force:
        print("Embeddings cache present; skipping (use --force to re-embed).")
        return
    clues = pd.read_parquet(config.PARQUET_PATH)
    instances = build_documents(clues)
    if limit is not None:
        instances = instances.head(limit).reset_index(drop=True)
    embeddings = embed_documents(instances["document"])
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.save(config.EMBEDDINGS_PATH, embeddings)
    instances.to_parquet(config.INSTANCES_PATH, index=False)
    print(f"Embedded {len(instances):,} instances -> {config.EMBEDDINGS_PATH}")
