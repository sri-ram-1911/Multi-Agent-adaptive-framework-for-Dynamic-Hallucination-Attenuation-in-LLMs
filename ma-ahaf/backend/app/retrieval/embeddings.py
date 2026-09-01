"""Sentence embeddings (DL). Falls back to a deterministic hashing embedder when
running fully offline (``MAAHAF_LLM__PROVIDER=mock``) so tests need no downloads.
"""

from __future__ import annotations

import hashlib
import threading

import numpy as np

from app.config import settings
from app.core.logging import get_logger
from app.db.models import EMBED_DIM

log = get_logger("embeddings")
_lock = threading.Lock()
_model = None
_offline = settings.llm.provider == "mock"


def _hash_embed(texts: list[str]) -> np.ndarray:
    """Bag-of-hashed-tokens embedding — cheap, deterministic, good enough offline."""
    out = np.zeros((len(texts), EMBED_DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        for tok in t.lower().split():
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            out[i, h % EMBED_DIM] += 1.0
        n = np.linalg.norm(out[i]) or 1.0
        out[i] /= n
    return out


def _load():
    global _model
    if _model is not None or _offline:
        return _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            log.info("embeddings.loading", model=settings.embedding_model)
            _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    if _offline:
        return _hash_embed(texts).tolist()
    model = _load()
    prefix = "Represent this sentence for searching relevant passages: " if is_query else ""
    vecs = model.encode(
        [prefix + t for t in texts], normalize_embeddings=True, show_progress_bar=False
    )
    return np.asarray(vecs, dtype=np.float32).tolist()


def embed_one(text: str, *, is_query: bool = False) -> list[float]:
    return embed([text], is_query=is_query)[0]
