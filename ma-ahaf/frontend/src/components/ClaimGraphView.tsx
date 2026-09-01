import { useMemo } from "react";
import ReactFlow, { Background, Controls, type Edge, type Node } from "reactflow";

interface Cyto {
  nodes: { data: Record<string, any> }[];
  edges: { data: Record<string, any> }[];
}

const RISK_COLOR = (r: number) =>
  r >= 0.6 ? "#fecaca" : r >= 0.35 ? "#fde68a" : "#bbf7d0";

export function ClaimGraphView({ graph }: { graph?: Cyto | null }) {
  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [] as Node[], edges: [] as Edge[] };
    const claims = graph.nodes.filter((n) => n.data.kind === "claim");
    const others = graph.nodes.filter((n) => n.data.kind !== "claim");
    const ns: Node[] = [
      ...claims.map((n, i) => ({
        id: n.data.id,
        position: { x: 40, y: i * 90 },
        data: { label: `${n.data.text?.slice(0, 48) ?? n.data.id}\n(${n.data.verdict ?? "?"})` },
        style: {
          background: RISK_COLOR(n.data.risk ?? 0),
          border: "1px solid #94a3b8",
          borderRadius: 8,
          fontSize: 11,
          width: 220,
          whiteSpace: "pre-wrap",
        },
      })),
      ...others.map((n, i) => ({
        id: n.data.id,
        position: { x: 340 + (i % 2) * 180, y: i * 55 },
        data: { label: `${n.data.kind}: ${String(n.data.text).slice(0, 20)}` },
        style: { background: "#f1f5f9", border: "1px dashed #cbd5e1", fontSize: 10, width: 150 },
      })),
    ];
    const es: Edge[] = graph.edges.map((e, i) => ({
      id: `e${i}`,
      source: e.data.source,
      target: e.data.target,
      label: e.data.kind,
      style: { stroke: e.data.kind === "depends_on" ? "#ef4444" : "#94a3b8" },
      labelStyle: { fontSize: 9 },
    }));
    return { nodes: ns, edges: es };
  }, [graph]);

  if (!graph || !nodes.length)
    return <div className="text-sm text-slate-400">No claim graph available.</div>;

  return (
    <div className="reactflow-wrapper h-[420px] rounded-lg border border-slate-200">
      <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.2}>
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
