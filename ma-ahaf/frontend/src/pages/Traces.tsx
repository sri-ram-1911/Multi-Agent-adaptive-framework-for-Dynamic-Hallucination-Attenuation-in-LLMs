import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ActionBadge, Card } from "../components/ui";

export function Traces() {
  const [action, setAction] = useState("");
  const q = useQuery({
    queryKey: ["traces", action],
    queryFn: () => api.traces({ limit: 100, action: action || undefined }),
  });

  return (
    <Card title="Requests">
      <div className="flex gap-2 mb-3">
        {["", "answer", "qualify", "abstain", "escalate"].map((a) => (
          <button
            key={a}
            onClick={() => setAction(a)}
            className={`text-xs px-2 py-1 rounded ${action === a ? "bg-blue-600 text-white" : "bg-slate-100"}`}
          >
            {a || "all"}
          </button>
        ))}
      </div>
      {q.isLoading && <div className="text-sm text-slate-400">loading…</div>}
      {q.error && <div className="text-sm text-rose-600">{(q.error as Error).message}</div>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b">
              <th className="py-2 pr-3">Time</th>
              <th className="py-2 pr-3">Prompt</th>
              <th className="py-2 px-2">Type</th>
              <th className="py-2 px-2">Action</th>
              <th className="py-2 px-2">Risk</th>
              <th className="py-2 px-2">Conf.</th>
              <th className="py-2 px-2">Disag.</th>
              <th className="py-2 px-2">Latency</th>
              <th className="py-2 px-2">Cost</th>
            </tr>
          </thead>
          <tbody>
            {q.data?.map((t) => (
              <tr key={t.trace_id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="py-2 pr-3 text-xs text-slate-400 whitespace-nowrap">
                  {new Date(t.created_at).toLocaleString()}
                </td>
                <td className="py-2 pr-3 max-w-sm truncate">
                  <Link className="text-blue-600" to={`/traces/${t.trace_id}`}>
                    {t.prompt}
                  </Link>
                </td>
                <td className="py-2 px-2 text-slate-500">{t.task_type}</td>
                <td className="py-2 px-2"><ActionBadge action={t.action} /></td>
                <td className="py-2 px-2">{t.max_claim_risk?.toFixed(2)}</td>
                <td className="py-2 px-2">{(t.calibrated_confidence ?? 0).toFixed(2)}</td>
                <td className="py-2 px-2">{(t.agent_disagreement ?? 0).toFixed(2)}</td>
                <td className="py-2 px-2">{t.latency_ms} ms</td>
                <td className="py-2 px-2">${(t.cost_usd ?? 0).toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
