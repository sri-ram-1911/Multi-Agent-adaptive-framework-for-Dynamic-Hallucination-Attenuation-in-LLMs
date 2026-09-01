import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { ParetoScatter } from "../components/ParetoScatter";
import { Card, Stat } from "../components/ui";

export function Evaluation() {
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["evalRuns"], queryFn: api.evalRuns, refetchInterval: 5000 });
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["evalRun", selected],
    queryFn: () => api.evalRun(selected!),
    enabled: !!selected,
  });
  const start = useMutation({
    mutationFn: () => api.startEval(20),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["evalRuns"] }),
  });

  const s = detail.data?.summary;
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center gap-3">
          <button
            onClick={() => start.mutate()}
            disabled={start.isPending}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50"
          >
            Run evaluation (20 items)
          </button>
          <span className="text-xs text-slate-400">
            MA-AHAF vs static-RAG baseline over data/benchmark/benchmark.jsonl
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {runs.data?.map((r) => (
            <button
              key={r.id}
              onClick={() => setSelected(r.id)}
              className={`text-xs px-2 py-1 rounded ${selected === r.id ? "bg-blue-600 text-white" : "bg-slate-100"}`}
            >
              {new Date(r.created_at).toLocaleTimeString()} · {r.status}
            </button>
          ))}
        </div>
      </Card>

      {s && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat
              label="Unsupported-claim rate Δ"
              value={fmtDelta(s.deltas?.unsupported_rate)}
              sub={`${s.ma_ahaf?.unsupported_rate} vs ${s.static_rag?.unsupported_rate}`}
            />
            <Stat
              label="Citation precision Δ"
              value={fmtDelta(s.deltas?.citation_precision, true)}
              sub={`${s.ma_ahaf?.citation_precision} vs ${s.static_rag?.citation_precision}`}
            />
            <Stat
              label="ECE (calibration) Δ"
              value={fmtDelta(s.deltas?.ece)}
              sub={`${s.ma_ahaf?.ece} vs ${s.static_rag?.ece}`}
            />
            <Stat
              label="Creativity Δ"
              value={fmtDelta(s.deltas?.creativity, true)}
              sub={`${s.ma_ahaf?.creativity} vs ${s.static_rag?.creativity}`}
            />
            <Stat label="Reliability index Δ" value={fmtDelta(s.deltas?.reliability, true)} />
            <Stat label="Pareto frontier gain" value={s.pareto_frontier_gain} />
            <Stat label="Abstention rate" value={s.ma_ahaf?.abstention_rate} />
            <Stat label="Avg latency" value={`${Math.round(s.ma_ahaf?.latency_ms || 0)} ms`} />
          </div>
          <Card title="Reliability–Creativity frontier">
            <ParetoScatter points={detail.data.pareto || []} />
            <p className="text-xs text-slate-400 mt-2">
              Each point is one benchmark item. Up-and-right is better. MA-AHAF should move the
              achievable frontier toward higher reliability without collapsing creativity.
            </p>
          </Card>
          <Card title="Full report">
            <pre className="text-xs bg-slate-900 text-slate-100 p-3 rounded overflow-x-auto max-h-96">
              {JSON.stringify(s, null, 2)}
            </pre>
          </Card>
        </>
      )}
    </div>
  );
}

function fmtDelta(v: number | undefined, higherIsBetter = false) {
  if (v === undefined) return "—";
  const good = higherIsBetter ? v > 0 : v < 0;
  return (
    <span className={good ? "text-emerald-600" : v === 0 ? "" : "text-rose-600"}>
      {v > 0 ? "+" : ""}
      {v.toFixed(3)}
    </span>
  );
}
