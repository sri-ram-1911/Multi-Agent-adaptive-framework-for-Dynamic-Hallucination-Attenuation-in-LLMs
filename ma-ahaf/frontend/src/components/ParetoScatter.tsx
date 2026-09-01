import {
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

interface Point {
  system: string;
  creativity: number;
  reliability: number;
  type?: string;
}

export function ParetoScatter({ points }: { points: Point[] }) {
  const maahaf = points.filter((p) => p.system === "ma-ahaf");
  const baseline = points.filter((p) => p.system === "static-rag");
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
        <CartesianGrid />
        <XAxis type="number" dataKey="creativity" name="Creativity" domain={[0, 1]}
          label={{ value: "Creativity", position: "insideBottom", offset: -10 }} />
        <YAxis type="number" dataKey="reliability" name="Reliability" domain={[0, 1]}
          label={{ value: "Reliability", angle: -90, position: "insideLeft" }} />
        <ZAxis range={[60, 60]} />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} />
        <Legend />
        <Scatter name="MA-AHAF" data={maahaf} fill="#2563eb" />
        <Scatter name="Static RAG" data={baseline} fill="#f97316" />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
