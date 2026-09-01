"""End-to-end pipeline test with retrieval stubbed (no Postgres needed)."""

from __future__ import annotations

import pytest

from app.orchestration import nodes as N
from app.orchestration.state import RequestState
from app.retrieval.schema import Evidence

_FAKE_DOCS = [
    "Water is H2O, two hydrogen atoms bonded to one oxygen atom. It boils at 100 degrees Celsius.",
    "The ACME Standard plan costs 29 US dollars per seat per month and includes the 99.9 percent SLA.",
]


@pytest.fixture(autouse=True)
def stub_retrieval(monkeypatch):
    def fake_retrieve(state: RequestState) -> RequestState:
        state.evidence = [
            Evidence(chunk_id=f"c{i}", document_id="d", document_title="Sample",
                     source="reference", text=t, rerank_score=0.8, fused_score=0.02,
                     source_score=0.8)
            for i, t in enumerate(_FAKE_DOCS)
        ]
        for c in state.claim_graph.claims:
            if c.claim_type not in ("creative", "opinion"):
                c.evidence_ids = ["c0", "c1"]
        state.signals.evidence_coverage = 1.0
        state.signals.source_agreement = 0.9
        return state

    monkeypatch.setattr(N, "n_retrieve", fake_retrieve)


def _run(prompt: str, **kw) -> RequestState:
    from app.orchestration.pipeline import run_pipeline

    return run_pipeline(db=None, tenant_id="t-test", prompt=prompt, persist=False, **kw)


def test_factual_request_completes_with_claims():
    st = _run("What is the chemical formula of water?")
    assert st.final_response
    assert st.action in ("answer", "qualify", "abstain", "escalate")
    assert len(st.claim_graph.claims) >= 1
    assert st.records[-1].agent == "audit"
    assert 0.0 <= st.calibrated_confidence <= 1.0


def test_creative_request_gets_high_creativity_allowance():
    st = _run("Write a two-line poem about the sea.")
    assert st.policy.creativity_allowance > 0.5
    assert st.task_type in ("creative", "mixed")


def test_high_stakes_request_uses_deep_verification():
    st = _run("What is the safe daily dose of warfarin for an adult patient?")
    assert st.policy.verification_depth > 0.5
    assert st.risk_score > 0.4


def test_pii_is_redacted_before_processing():
    st = _run("My email is alice@example.com, what is the water formula?")
    assert "alice@example.com" not in st.prompt
    assert "EMAIL" in st.pii_flags


def test_audit_trace_is_assembled():
    st = _run("What does the ACME Standard plan cost?")
    trace = st.__dict__.get("_audit_trace")
    assert trace and trace["action"] == st.action
    assert "claim_graph" in trace
    assert len(trace["agent_runs"]) >= 10
