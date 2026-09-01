"""Shared retrieval data types."""

from __future__ import annotations

from pydantic import BaseModel


class Evidence(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    source: str
    text: str
    # retrieval scores
    vector_score: float = 0.0
    keyword_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float = 0.0
    # source-quality (filled by SourceQualityAgent)
    source_score: float = 0.5
    authority: float = 0.5
    freshness: float = 0.5
    stance: str = "neutral"  # support / contradict / neutral  (filled by verification)

    class Config:
        frozen = False
