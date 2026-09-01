import type { SegmentOut } from "../lib/types";

const KIND_STYLE: Record<string, string> = {
  factual: "border-l-emerald-400 bg-emerald-50",
  assumption: "border-l-amber-400 bg-amber-50",
  creative: "border-l-violet-400 bg-violet-50",
};

export function SegmentedAnswer({
  response,
  segments,
}: {
  response: string;
  segments: SegmentOut[];
}) {
  return (
    <div className="space-y-3">
      <div className="whitespace-pre-wrap text-sm leading-relaxed">{response}</div>
      {segments.length > 0 && (
        <div className="pt-2 border-t border-slate-100">
          <div className="text-xs font-semibold text-slate-400 mb-2">
            Claim segmentation (factual / assumption / creative)
          </div>
          <div className="space-y-1.5">
            {segments.map((s, i) => (
              <div
                key={i}
                className={`border-l-4 pl-3 py-1 text-sm rounded ${KIND_STYLE[s.kind] || "border-l-slate-300"}`}
              >
                <span className="text-[10px] uppercase tracking-wide text-slate-500 mr-2">
                  {s.kind}
                  {s.supported === true ? " ✓" : s.supported === false ? " ✕" : ""}
                </span>
                {s.text}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
