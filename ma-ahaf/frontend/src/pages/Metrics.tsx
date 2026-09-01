import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { Card, Stat } from "../components/ui";

export function Metrics() {
  const q = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 15000 });
  const esc = useQuery({ queryKey: ["escalations"], queryFn: api.escalations });
  if (q.isLoading) return <div className="text-sm text-slate-400">loading…</div>;
  if (q.error) return <div className="text-sm text-rose-600">{(q.error as Error).message}</div>;
  const m = q.data!;
  const actionData = Object.entries(m.by_action).map(([action, count]) => ({ action, count }));
  const ts = m.timeseries.map((p) => ({ ...p, t: new Date(p.t).toLocaleTimeString() }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Requests (7d)" value={m.total_requests} />
        <Stat label="Abstain + escalate" value={`${(m.abstention_rate * 100).toFixed(1)}%`} />
        <Stat label="Avg calibrated conf." value={m.avg_calibrated_confidence.toFixed(2)} />
        <Stat label="Avg max claim risk" value={m.avg_max_claim_risk.toFixed(2)} />
        <Stat label="Latency p50 / p95" value={`${m.latency_ms.p50} / ${m.latency_ms.p95} ms`} />
        <Stat label="Avg disagreement" value={m.avg_agent_disagreement.toFixed(2)} />
        <Stat label="Tokens (7d)" value={m.tokens_total.toLocaleString()} />
        <Stat label="Cost (7d)" value={`$${m.cost_usd_total.toFixed(3)}`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Requests by action">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={actionData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="action" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Latency over time (ms)">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={ts}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="t" hide />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="latency_ms" stroke="#2563eb" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Max claim risk over time">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={ts}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="t" hide />
              <YAxis domain={[0, 1]} />
              <Tooltip />
              <Line type="monotone" dataKey="risk" stroke="#ef4444" dot={false} />
              <Line type="monotone" dataKey="confidence" stroke="#10b981" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title={`Escalation queue (${esc.data?.length ?? 0})`}>
          <div className="space-y-1 text-sm">
            {(esc.data || []).map((e) => (
              <div key={e.id} className="flex justify-between border-b border-slate-100 py-1">
                <a className="text-blue-600" href={`/traces/${e.request_id}`}>
                  {e.request_id.slice(0, 8)}
                </a>
                <span className="text-slate-500">{e.reason}</span>
                <span className="text-xs text-slate-400">{new Date(e.created_at).toLocaleString()}</span>
              </div>
            ))}
            {!esc.data?.length && <div className="text-slate-400">Nothing pending.</div>}
          </div>
        </Card>
      </div>
      <p className="text-xs text-slate-400">
        Prometheus metrics: <code>/metrics</code> · Grafana: <code>make up-obs</code> → localhost:3000
      </p>
    </div>
  );
}
