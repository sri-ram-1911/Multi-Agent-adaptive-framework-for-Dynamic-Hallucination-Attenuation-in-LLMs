import { useState } from "react";

interface Run {
  agent: string;
  ordinal: number;
  output: Record<string, any>;
  rationale?: string;
  latency_ms: number;
  tokens: number;
  model_version?: string;
}

export function AgentTimeline({ runs }: { runs: Run[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const max = Math.max(1, ...runs.map((r) => r.latency_ms));
  return (
    <div className="space-y-1.5">
      {runs.map((r, i) => (
        <div key={i} className="text-sm">
          <div
            className="flex items-center gap-3 cursor-pointer hover:bg-slate-50 rounded px-2 py-1"
            onClick={() => setOpen(open === i ? null : i)}
          >
            <span className="w-40 shrink-0 font-medium">
              {r.ordinal + 1}. {r.agent}
            </span>
            <div className="flex-1 h-2 bg-slate-100 rounded overflow-hidden">
              <div
                className="h-full bg-blue-400"
                style={{ width: `${(r.latency_ms / max) * 100}%` }}
              />
            </div>
            <span className="w-16 text-right text-xs text-slate-400">{r.latency_ms} ms</span>
            <span className="w-16 text-right text-xs text-slate-400">{r.tokens} tok</span>
          </div>
          {open === i && (
            <pre className="mx-2 mt-1 p-2 bg-slate-900 text-slate-100 text-[11px] rounded overflow-x-auto">
              {r.model_version ? `model: ${r.model_version}\n` : ""}
              {r.rationale ? `rationale: ${r.rationale}\n\n` : ""}
              {JSON.stringify(r.output, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
