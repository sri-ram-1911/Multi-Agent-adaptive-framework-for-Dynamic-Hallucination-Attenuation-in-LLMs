import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { AgentTimeline } from "../components/AgentTimeline";
import { ClaimsTable } from "../components/ClaimsTable";
import { PolicyRadar } from "../components/PolicyRadar";
import { SegmentedAnswer } from "../components/SegmentedAnswer";
import { ActionBadge, Card, Stat } from "../components/ui";
import type { GenerateResponse } from "../lib/types";

const EXAMPLES = [
  "What is the recommended daily water intake for adults?",
  "Our customer bought an annual ACME Cloud plan 20 days ago and wants a full refund. What are they entitled to?",
  "What is the safe daily dose of warfarin for an adult?",
  "Write a two-line poem about a raindrop returning to the sea.",
  "Summarise ACME's annual refund rules, then draft a friendly message for a customer just past the 14-day window.",
];

export function Playground() {
  const [prompt, setPrompt] = useState(EXAMPLES[0]);
  const [profile, setProfile] = useState("balanced");
  const [creativity, setCreativity] = useState<number | "">("");

  const mut = useMutation({
    mutationFn: () =>
      api.generate({
        prompt,
        policy_profile: profile,
        policy_overrides: creativity === "" ? {} : { creativity_allowance: Number(creativity) },
      }),
  });
  const r: GenerateResponse | undefined = mut.data;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        <Card title="Prompt">
          <textarea
            className="w-full border border-slate-200 rounded-lg p-3 text-sm h-28"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="flex flex-wrap gap-2 mt-2">
            {EXAMPLES.map((e) => (
              <button
                key={e}
                onClick={() => setPrompt(e)}
                className="text-xs px-2 py-1 bg-slate-100 rounded hover:bg-slate-200"
              >
                {e.slice(0, 42)}…
              </button>
            ))}
          </div>
          <div className="flex items-center gap-4 mt-3">
            <label className="text-sm">
              Profile{" "}
              <select
                className="border rounded px-2 py-1 text-sm"
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
              >
                <option>strict</option>
                <option>balanced</option>
                <option>creative</option>
              </select>
            </label>
            <label className="text-sm">
              Creativity override{" "}
              <input
                type="number"
                step="0.1"
                min="0"
                max="1"
                placeholder="auto"
                className="border rounded px-2 py-1 w-20 text-sm"
                value={creativity}
                onChange={(e) => setCreativity(e.target.value === "" ? "" : Number(e.target.value))}
              />
            </label>
            <button
              onClick={() => mut.mutate()}
              disabled={mut.isPending}
              className="ml-auto bg-blue-600 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50"
            >
              {mut.isPending ? "Running agents…" : "Generate"}
            </button>
          </div>
        </Card>

        {mut.isError && (
          <Card>
            <div className="text-rose-600 text-sm">{(mut.error as Error).message}</div>
          </Card>
        )}

        {r && (
          <>
            <Card>
              <div className="flex items-center gap-3 mb-3">
                <ActionBadge action={r.action} />
                <span className="text-xs text-slate-500">{r.action_reason}</span>
                <Link to={`/traces/${r.trace_id}`} className="ml-auto text-xs text-blue-600">
                  full trace →
                </Link>
              </div>
              <SegmentedAnswer response={r.response} segments={r.segments} />
            </Card>

            <Card title={`Claims (${r.claims.length})`}>
              <ClaimsTable claims={r.claims} />
            </Card>

            <Card title={`Evidence (${r.evidence.length})`}>
              <div className="space-y-2">
                {r.evidence.map((e) => (
                  <div key={e.chunk_id} className="text-xs border-l-2 border-slate-200 pl-2">
                    <div className="flex gap-2 text-slate-400">
                      <span className="font-medium text-slate-600">{e.document_title}</span>
                      <span>src {e.source_score.toFixed(2)}</span>
                      <span>rerank {e.rerank_score.toFixed(2)}</span>
                      {e.stance !== "neutral" && (
                        <span className={e.stance === "contradict" ? "text-rose-500" : "text-emerald-600"}>
                          {e.stance}
                        </span>
                      )}
                    </div>
                    {e.text.slice(0, 240)}
                  </div>
                ))}
              </div>
            </Card>
          </>
        )}
      </div>

      <div className="space-y-4">
        {r && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Calibrated conf." value={`${(r.calibrated_confidence * 100).toFixed(0)}%`} sub={`raw ${(r.confidence * 100).toFixed(0)}%`} />
              <Stat label="Max claim risk" value={r.max_claim_risk.toFixed(2)} />
              <Stat label="Task" value={r.task_type} sub={`risk ${r.risk_score.toFixed(2)}`} />
              <Stat label="Disagreement" value={r.agent_disagreement.toFixed(2)} />
              <Stat label="Creativity" value={r.creativity_score.toFixed(2)} />
              <Stat label="Latency" value={`${r.latency_ms} ms`} sub={`$${(r.usage.cost_usd ?? 0).toFixed(4)}`} />
            </div>
            <Card title="Policy vector (ARCOP)">
              <PolicyRadar policy={r.policy_vector} />
              <p className="text-[11px] text-slate-400 mt-2">{r.policy_vector.rationale}</p>
            </Card>
            <Card title="Agent timeline">
              <AgentTimelineFromResponse traceId={r.trace_id} />
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

function AgentTimelineFromResponse({ traceId }: { traceId: string }) {
  const q = useQuery({ queryKey: ["trace", traceId], queryFn: () => api.trace(traceId) });
  if (q.isLoading) return <div className="text-xs text-slate-400">loading…</div>;
  return <AgentTimeline runs={q.data?.agent_runs || []} />;
}
