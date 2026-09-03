import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { ClaimGraphView } from "../components/ClaimGraphView";
import { ActionBadge, Card, RiskBadge, Stat, VerdictBadge } from "../components/ui";

export function Review() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"pending" | "reviewed">("pending");
  const [selected, setSelected] = useState<string | null>(null);
  const stats = useQuery({ queryKey: ["reviewStats"], queryFn: api.reviewStats, refetchInterval: 8000 });
  const list = useQuery({
    queryKey: ["reviewQueue", tab],
    queryFn: () => api.reviewQueue(tab),
    refetchInterval: 8000,
  });
  const item = useQuery({
    queryKey: ["reviewItem", selected],
    queryFn: () => api.reviewItem(selected!),
    enabled: !!selected,
  });

  const [note, setNote] = useState("");
  const [revised, setRevised] = useState("");
  const resolve = useMutation({
    mutationFn: (decision: string) =>
      api.resolveReview(selected!, {
        decision,
        note,
        revised_response: decision === "revised" ? revised : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviewQueue"] });
      qc.invalidateQueries({ queryKey: ["reviewStats"] });
      qc.invalidateQueries({ queryKey: ["reviewItem", selected] });
      qc.invalidateQueries({ queryKey: ["traces"] });
      setNote("");
      setRevised("");
      setSelected(null);
    },
  });

  const d = item.data;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Pending review" value={stats.data?.pending ?? "—"} />
        <Stat label="Reviewed" value={stats.data?.reviewed ?? "—"} />
        <Stat label="Showing" value={tab} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title="Queue" className="lg:col-span-1">
          <div className="flex gap-2 mb-3">
            {(["pending", "reviewed"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`text-xs px-2 py-1 rounded ${tab === t ? "bg-blue-600 text-white" : "bg-slate-100"}`}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="space-y-1.5">
            {list.data?.length === 0 && (
              <div className="text-sm text-slate-400">Nothing {tab}.</div>
            )}
            {list.data?.map((q) => (
              <button
                key={q.id}
                onClick={() => setSelected(q.id)}
                className={`w-full text-left border rounded-lg p-2 text-sm hover:bg-slate-50 ${
                  selected === q.id ? "border-blue-500 bg-blue-50" : "border-slate-200"
                }`}
              >
                <div className="flex items-center gap-2">
                  <ActionBadge action={q.action} />
                  <RiskBadge level={q.max_claim_risk >= 0.6 ? "high" : q.max_claim_risk >= 0.35 ? "medium" : "low"} score={q.max_claim_risk} />
                  {q.decision && <span className="badge bg-slate-100 text-slate-600">{q.decision}</span>}
                </div>
                <div className="mt-1 line-clamp-2">{q.prompt}</div>
                <div className="text-xs text-slate-400 mt-1">{q.reason}</div>
              </button>
            ))}
          </div>
        </Card>

        <div className="lg:col-span-2 space-y-4">
          {!d && <Card><div className="text-sm text-slate-400">Select an item to review.</div></Card>}
          {d && (
            <>
              <Card>
                <div className="flex items-center gap-2 mb-2">
                  <ActionBadge action={d.action} />
                  <span className="text-xs text-slate-400">{d.reason}</span>
                </div>
                <div className="text-sm font-medium">{d.prompt}</div>
                <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                  <div>calibrated conf: <b>{(d.calibrated_confidence ?? 0).toFixed(2)}</b></div>
                  <div>max claim risk: <b>{(d.max_claim_risk ?? 0).toFixed(2)}</b></div>
                  <div>disagreement: <b>{(d.agent_disagreement ?? 0).toFixed(2)}</b></div>
                </div>
                <div className="mt-3 whitespace-pre-wrap text-sm bg-slate-50 p-3 rounded">
                  {d.final_response}
                </div>
              </Card>

              <Card title="Claims">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <tbody>
                      {(d.claims || []).map((c: any, i: number) => (
                        <tr key={i} className="border-b border-slate-100">
                          <td className="py-1 pr-2 max-w-md">{c.text}</td>
                          <td className="py-1 px-2"><VerdictBadge verdict={c.verdict} /></td>
                          <td className="py-1 px-2"><RiskBadge level={c.risk_level} score={c.risk_score} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              {d.claim_graph && (
                <Card title="Claim Risk Graph">
                  <ClaimGraphView graph={d.claim_graph} />
                </Card>
              )}

              {d.status === "reviewed" ? (
                <Card>
                  <div className="text-sm">
                    Reviewed: <b>{d.decision}</b> by {d.reviewed_by}
                    {d.review_note && <div className="text-slate-500 mt-1">"{d.review_note}"</div>}
                  </div>
                </Card>
              ) : (
                <Card title="Decision">
                  <textarea
                    className="w-full border border-slate-200 rounded p-2 text-sm h-20"
                    placeholder="Reviewer note (why)"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                  <textarea
                    className="w-full border border-slate-200 rounded p-2 text-sm h-24 mt-2"
                    placeholder="Revised answer (only needed for 'Revise & release')"
                    value={revised}
                    onChange={(e) => setRevised(e.target.value)}
                  />
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => resolve.mutate("approved")}
                      disabled={resolve.isPending}
                      className="bg-emerald-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
                    >
                      Approve & release
                    </button>
                    <button
                      onClick={() => resolve.mutate("revised")}
                      disabled={resolve.isPending || !revised}
                      className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
                    >
                      Revise & release
                    </button>
                    <button
                      onClick={() => resolve.mutate("rejected")}
                      disabled={resolve.isPending}
                      className="bg-rose-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
                    >
                      Reject & withhold
                    </button>
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
