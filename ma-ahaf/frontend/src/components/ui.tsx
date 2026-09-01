import type { ReactNode } from "react";

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div className={`card ${className}`}>
      {title && <h3 className="text-sm font-semibold text-slate-500 mb-3">{title}</h3>}
      {children}
    </div>
  );
}

const ACTION_COLORS: Record<string, string> = {
  answer: "bg-emerald-100 text-emerald-800",
  qualify: "bg-amber-100 text-amber-800",
  abstain: "bg-orange-100 text-orange-800",
  escalate: "bg-rose-100 text-rose-800",
};

export function ActionBadge({ action }: { action: string }) {
  return <span className={`badge ${ACTION_COLORS[action] || "bg-slate-100 text-slate-700"}`}>{action}</span>;
}

const RISK_COLORS: Record<string, string> = {
  low: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-rose-100 text-rose-800",
};

export function RiskBadge({ level, score }: { level: string; score?: number }) {
  return (
    <span className={`badge ${RISK_COLORS[level] || "bg-slate-100"}`}>
      {level}
      {score !== undefined ? ` ${score.toFixed(2)}` : ""}
    </span>
  );
}

const VERDICT_COLORS: Record<string, string> = {
  supported: "bg-emerald-100 text-emerald-800",
  refuted: "bg-rose-100 text-rose-800",
  insufficient: "bg-amber-100 text-amber-800",
  unverified: "bg-slate-100 text-slate-600",
};

export function VerdictBadge({ verdict }: { verdict: string }) {
  return <span className={`badge ${VERDICT_COLORS[verdict] || "bg-slate-100"}`}>{verdict}</span>;
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}
