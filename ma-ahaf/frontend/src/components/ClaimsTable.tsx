import { Fragment, useState } from "react";
import type { ClaimOut } from "../lib/types";
import { RiskBadge, VerdictBadge } from "./ui";

export function ClaimsTable({ claims }: { claims: ClaimOut[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!claims.length) return <div className="text-sm text-slate-400">No claims extracted.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-400 border-b border-slate-200">
            <th className="py-2 pr-3">Claim</th>
            <th className="py-2 px-2">Type</th>
            <th className="py-2 px-2">Crit.</th>
            <th className="py-2 px-2">Verdict</th>
            <th className="py-2 px-2">Risk</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((c) => (
            <Fragment key={c.id}>
              <tr
                className="border-b border-slate-100 cursor-pointer hover:bg-slate-50"
                onClick={() => setOpen(open === c.id ? null : c.id)}
              >
                <td className="py-2 pr-3 max-w-md">{c.text}</td>
                <td className="py-2 px-2 text-slate-500">{c.claim_type}</td>
                <td className="py-2 px-2">{c.criticality.toFixed(2)}</td>
                <td className="py-2 px-2">
                  <VerdictBadge verdict={c.verdict} />
                </td>
                <td className="py-2 px-2">
                  <RiskBadge level={c.risk_level} score={c.risk_score} />
                </td>
              </tr>
              {open === c.id && (
                <tr className="bg-slate-50">
                  <td colSpan={5} className="px-3 py-2 text-xs text-slate-600">
                    <div className="mb-1 font-medium">{c.explanation}</div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(c.risk_contributions).map(([k, v]) => (
                        <span key={k} className="badge bg-white border border-slate-200">
                          {k}: {v > 0 ? "+" : ""}
                          {v.toFixed(2)}
                        </span>
                      ))}
                    </div>
                    <div className="mt-1 text-slate-400">
                      evidence: {c.evidence_ids.join(", ") || "none"}
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
