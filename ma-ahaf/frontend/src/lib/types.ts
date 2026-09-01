export type Action = "answer" | "qualify" | "abstain" | "escalate";

export interface PolicyVector {
  grounding_intensity: number;
  verification_depth: number;
  creativity_allowance: number;
  citation_requirement: number;
  abstention_threshold: number;
  escalation_threshold: number;
  candidates: number;
  rationale: string;
}

export interface ClaimOut {
  id: string;
  text: string;
  claim_type: string;
  criticality: number;
  verdict: string;
  risk_score: number;
  risk_level: string;
  risk_contributions: Record<string, number>;
  evidence_ids: string[];
  explanation: string;
}

export interface EvidenceOut {
  chunk_id: string;
  document_title: string;
  source: string;
  text: string;
  source_score: number;
  rerank_score: number;
  stance: string;
}

export interface SegmentOut {
  kind: "factual" | "assumption" | "creative";
  text: string;
  supported: boolean | null;
}

export interface GenerateResponse {
  trace_id: string;
  response: string;
  segments: SegmentOut[];
  action: Action;
  action_reason: string;
  confidence: number;
  calibrated_confidence: number;
  consistency_gap: number;
  task_type: string;
  risk_score: number;
  max_claim_risk: number;
  agent_disagreement: number;
  creativity_score: number;
  policy_vector: PolicyVector;
  claims: ClaimOut[];
  evidence: EvidenceOut[];
  usage: Record<string, number>;
  latency_ms: number;
}

export interface TraceListItem {
  trace_id: string;
  created_at: string;
  prompt: string;
  task_type: string;
  action: Action;
  risk_score: number;
  max_claim_risk: number;
  agent_disagreement: number;
  calibrated_confidence: number;
  latency_ms: number;
  total_tokens: number;
  cost_usd: number;
}

export interface MetricsSummary {
  total_requests: number;
  by_action: Record<string, number>;
  abstention_rate: number;
  avg_calibrated_confidence: number;
  avg_max_claim_risk: number;
  avg_agent_disagreement: number;
  latency_ms: { p50: number; p90: number; p95: number };
  tokens_total: number;
  cost_usd_total: number;
  avg_verification_depth: number | null;
  timeseries: {
    t: string;
    latency_ms: number;
    risk: number;
    confidence: number;
    action: string;
  }[];
}
