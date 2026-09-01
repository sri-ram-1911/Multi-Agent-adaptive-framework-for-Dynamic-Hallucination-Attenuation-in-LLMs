from __future__ import annotations

import numpy as np

from app.nlp.nli import entail
from app.retrieval.embeddings import embed_one
from app.retrieval.hybrid import _rrf
from app.retrieval.reranker import rerank
from app.retrieval.schema import Evidence


def test_hash_embeddings_shape_and_norm():
    v = embed_one("the quick brown fox")
    assert len(v) == 384
    assert abs(np.linalg.norm(v) - 1.0) < 1e-5


def test_rrf_fuses_rankings():
    a = [Evidence(chunk_id="1", document_id="d", document_title="t", source="s", text="x")]
    b = [Evidence(chunk_id="1", document_id="d", document_title="t", source="s", text="x"),
         Evidence(chunk_id="2", document_id="d", document_title="t", source="s", text="y")]
    fused = _rrf([a, b])
    assert fused["1"].fused_score > fused["2"].fused_score


def test_reranker_offline_orders_by_overlap():
    evs = [
        Evidence(chunk_id="1", document_id="d", document_title="t", source="s", text="water boils at 100"),
        Evidence(chunk_id="2", document_id="d", document_title="t", source="s", text="unrelated text here"),
    ]
    ranked = rerank("what temperature does water boil", evs, top_k=2)
    assert ranked[0].chunk_id == "1"


def test_nli_heuristic_detects_contradiction():
    r = entail("The service is available.", "The service is not available.")
    assert r["contradiction"] >= r["entailment"]
