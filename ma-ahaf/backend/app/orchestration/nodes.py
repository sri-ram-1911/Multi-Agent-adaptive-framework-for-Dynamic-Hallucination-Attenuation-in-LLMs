"""Graph nodes: thin wrappers around agents + a few pure aggregation steps."""

from __future__ import annotations

from app.agents.a01_intent_classifier import IntentClassifier
from app.agents.a02_risk_profiler import RiskProfiler
from app.agents.a03_policy_controller import PolicyController
from app.agents.a04_candidate_generator import CandidateGenerator
from app.agents.a05_claim_decomposer import ClaimDecomposer
from app.agents.a06_evidence_retrieval import EvidenceRetrieval
from app.agents.a07_source_quality import SourceQuality
from app.agents.a08_verification import Verification
from app.agents.a09_contradiction import Contradiction
from app.agents.a10_creativity import Creativity
from app.agents.a11_revision import Revision
from app.agents.a12_abstention import Abstention
from app.agents.a13_audit import Audit
from app.claimgraph.graph import propagate_risk
from app.controller.risk_model import score_claim
from app.core.telemetry import (
    ABSTENTIONS,
    AGENT_DISAGREEMENT,
    HALLUCINATION_RISK,
    VERIFICATION_DEPTH,
)
from app.orchestration.state import RequestState, ResponseSegment


def needs_revision(s: RequestState) -> str:
    """Conditional edge after the creativity node: revise vs decide."""
    from app.config import settings

    if s.revision_loops >= settings.max_revision_loops:
        return "decide"
    cg = s.claim_graph
    problem = cg.critical_unsupported() or [
        c for c in cg.claims if c.risk_level == "high" or c.contradiction_score > 0.55
    ]
    if problem and not (
        s.policy and s.policy.creativity_allowance > 0.7 and not cg.critical_unsupported()
    ):
        return "revise"
    return "decide"


intent = IntentClassifier()
risk_profiler = RiskProfiler()
policy_controller = PolicyController()
candidate_generator = CandidateGenerator()
claim_decomposer = ClaimDecomposer()
evidence_retrieval = EvidenceRetrieval()
source_quality = SourceQuality()
verification = Verification()
contradiction = Contradiction()
creativity = Creativity()
revision = Revision()
abstention = Abstention()
audit = Audit()


def n_intent(s: RequestState) -> RequestState:
    return intent.run(s)


def n_risk(s: RequestState) -> RequestState:
    return risk_profiler.run(s)


def n_policy(s: RequestState) -> RequestState:
    s = policy_controller.run(s)
    VERIFICATION_DEPTH.observe(s.policy.depth_bucket if s.policy else 1)
    return s


def n_pre_retrieve(s: RequestState) -> RequestState:
    """Selective grounding-first retrieval (proposal §11): when the policy calls for
    high grounding, fetch prompt-level context so the draft is grounded from the
    start instead of generate-then-check. Skipped for creativity-first requests."""
    if not s.policy or s.policy.grounding_intensity < 0.55 or s.db is None:
        return s
    from app.retrieval.hybrid import HybridRetriever

    s.evidence = HybridRetriever(s.db).retrieve(
        s.prompt, tenant_id=s.tenant_id, rerank_k=5,
        grounding_intensity=s.policy.grounding_intensity,
    )
    return s


def n_generate(s: RequestState) -> RequestState:
    return candidate_generator.run(s)


def n_decompose(s: RequestState) -> RequestState:
    return claim_decomposer.run(s)


def n_retrieve(s: RequestState) -> RequestState:
    s = evidence_retrieval.run(s)
    return source_quality.run(s)


def n_verify(s: RequestState) -> RequestState:
    s = verification.run(s)
    return contradiction.run(s)


def n_risk_scoring(s: RequestState) -> RequestState:
    """Claim Risk Graph: score H(x) per claim, then propagate along dependencies."""
    for claim in s.claim_graph.claims:
        score_claim(claim)
    propagate_risk(s.claim_graph)
    s.risk_factors["max_claim_risk"] = round(s.claim_graph.max_risk(), 3)
    HALLUCINATION_RISK.observe(s.claim_graph.max_risk())
    return s


def n_creativity(s: RequestState) -> RequestState:
    return creativity.run(s)


def n_revise(s: RequestState) -> RequestState:
    return revision.run(s)


def n_decide(s: RequestState) -> RequestState:
    s = abstention.run(s)
    AGENT_DISAGREEMENT.set(s.agent_disagreement)
    return s


def n_finalize(s: RequestState) -> RequestState:
    """Assemble the user-facing response from the (possibly revised) draft."""
    draft = s.chosen_candidate
    if s.action == "abstain":
        missing = "; ".join(c.text for c in s.claim_graph.critical_unsupported()[:3])
        s.final_response = (
            "I don't have sufficient reliable evidence to answer this confidently.\n\n"
            f"Specifically, these points could not be verified: {missing}.\n\n"
            "You could narrow the question, provide a source, or ask for a best-effort "
            "answer explicitly labelled as unverified."
        )
        s.segments = [ResponseSegment(kind="assumption", text=s.final_response)]
    elif s.action in ("qualify", "escalate"):
        banner = {
            "qualify": f"⚠️ Answered with uncertainty ({s.action_reason}). "
                       f"Calibrated confidence: {s.calibrated_confidence:.0%}.",
            "escalate": "⚠️ This response is queued for human review due to unresolved "
                        "disagreement between verification agents. Draft answer below.",
        }[s.action]
        s.final_response = f"{banner}\n\n{draft}"
    else:
        s.final_response = draft

    ABSTENTIONS.labels(kind=s.action).inc()
    return audit.run(s)
