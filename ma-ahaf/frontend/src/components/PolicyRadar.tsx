import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import type { PolicyVector } from "../lib/types";

export function PolicyRadar({ policy }: { policy: PolicyVector }) {
  const data = [
    { k: "Grounding", v: policy.grounding_intensity },
    { k: "Verification", v: policy.verification_depth },
    { k: "Creativity", v: policy.creativity_allowance },
    { k: "Citation", v: policy.citation_requirement },
    { k: "Abstention", v: policy.abstention_threshold },
    { k: "Escalation", v: policy.escalation_threshold },
  ];
  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={data} outerRadius="70%">
        <PolarGrid />
        <PolarAngleAxis dataKey="k" tick={{ fontSize: 11 }} />
        <Radar dataKey="v" stroke="#2563eb" fill="#3b82f6" fillOpacity={0.35} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
