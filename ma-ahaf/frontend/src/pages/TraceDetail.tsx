import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { AgentTimeline } from "../components/AgentTimeline";
import { ClaimGraphView } from "../components/ClaimGraphView";
import { PolicyRadar } from "../components/PolicyRadar";
import { ActionBadge, Card, RiskBadge, Stat, VerdictBadge } from "../components/ui";

export function TraceDetail() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["trace", id], queryFn: () => api.trace(id!) });
  if (q.isLoading) return <div className="text-sm text-slate-400">loading…</div>;
  if (q.error) return <div className="text-sm text-rose-600">{(q.error as Error).message}</div>;
  const t = q.data;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center gap-3">
          <ActionBadge action={t.action} />
          {t.escalated && <span className="badge bg-rose-100 text-rose-800">escalated</span>}
          <span className="text-xs text-slate-400">{t.trace_id}</span>
        </div>
        <div className="mt-2 text-sm font-medium">{t.prompt}</div>
        <div className="mt-3 whitespace-pre-wrap text-sm bg-slate-50 p-3 rounded">{t.final_response}</div>
        {t.pii_flags?.length > 0 && (
          <div className="mt-2 text-xs text-amber-600">PII redacted: {t.pii_flags.join(", ")}</div>
        )}
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Calibrated conf." value={(t.calibrated_confidence ?? 0).toFixed(2)} sub={`raw ${(t.confidence ?? 0).toFixed(2)}`} />
        <Stat label="Request risk" value={(t.risk_score ?? 0).toFixed(2)} />
        <Stat label="Max claim risk" value={(t.max_claim_risk ?? 0).toFixed(2)} />
        <Stat label="Disagreement" value={(t.agent_disagreement ?? 0).toFixed(2)} />
        <Stat label="Latency" value={`${t.latency_ms} ms`} />
        <Stat label="Tokens" value={t.total_tokens} />
        <Stat label="Cost" value={`$${(t.cost_usd ?? 0).toFixed(4)}`} />
        <Stat label="Task" value={t.task_type} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Policy vector (ARCOP)">
          <PolicyRadar policy={t.policy_vector} />
        </Card>
        <Card title="Claim Risk Graph">
          <ClaimGraphView graph={t.claim_graph} />
        </Card>
      </div>

      <Card title={`Claims (${t.claims?.length ?? 0})`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400 border-b">
                <th className="py-2 pr-3">Claim</th>
                <th className="py-2 px-2">Type</th>
                <th className="py-2 px-2">Verdict</th>
                <th className="py-2 px-2">Risk</th>
                <th className="py-2 px-2">Dominant factors</th>
              </tr>
            </thead>
            <tbody>
              {t.claims?.map((c: any) => (
                <tr key={c.id} className="border-b border-slate-100">
                  <td className="py-2 pr-3 max-w-md">{c.text}</td>
                  <td className="py-2 px-2 text-slate-500">{c.claim_type}</td>
                  <td className="py-2 px-2"><VerdictBadge verdict={c.verdict} /></td>
                  <td className="py-2 px-2"><RiskBadge level={c.risk_level} score={c.risk_score} /></td>
                  <td className="py-2 px-2 text-xs text-slate-500">
                    {Object.entries(c.risk_contributions || {})
                      .sort((a: any, b: any) => b[1] - a[1])
                      .slice(0, 2)
                      .map(([k, v]: any) => `${k} ${v > 0 ? "+" : ""}${v.toFixed(2)}`)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Agent timeline">
        <AgentTimeline runs={t.agent_runs || []} />
      </Card>

      <Card title="Model versions (reproducibility)">
        <pre className="text-xs bg-slate-900 text-slate-100 p-3 rounded overflow-x-auto">
          {JSON.stringify(t.model_versions, null, 2)}
        </pre>
      </Card>
    </div>
  );
}
