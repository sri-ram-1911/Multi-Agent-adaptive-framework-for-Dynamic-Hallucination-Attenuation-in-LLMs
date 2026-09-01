import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { Card } from "../components/ui";

export function KnowledgeBase() {
  const qc = useQueryClient();
  const docs = useQuery({ queryKey: ["kbDocs"], queryFn: api.kbDocuments });
  const [query, setQuery] = useState("");
  const search = useQuery({
    queryKey: ["kbSearch", query],
    queryFn: () => api.kbSearch(query, 6),
    enabled: false,
  });
  const [form, setForm] = useState({ title: "", source: "doc", text: "", authority: 0.6 });
  const ingest = useMutation({
    mutationFn: () => api.kbIngest(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kbDocs"] });
      setForm({ title: "", source: "doc", text: "", authority: 0.6 });
    },
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title={`Documents (${docs.data?.length ?? 0})`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b">
              <th className="py-1">Title</th>
              <th className="py-1">Source</th>
              <th className="py-1">Authority</th>
              <th className="py-1">Chunks</th>
            </tr>
          </thead>
          <tbody>
            {docs.data?.map((d) => (
              <tr key={d.id} className="border-b border-slate-100">
                <td className="py-1">{d.title}</td>
                <td className="py-1 text-slate-500">{d.source}</td>
                <td className="py-1">{d.authority?.toFixed(2)}</td>
                <td className="py-1">{d.chunks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Add document">
        <div className="space-y-2">
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Title"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Source (e.g. policy, product-doc)"
            value={form.source}
            onChange={(e) => setForm({ ...form, source: e.target.value })}
          />
          <textarea
            className="w-full border rounded px-2 py-1 text-sm h-32"
            placeholder="Document text"
            value={form.text}
            onChange={(e) => setForm({ ...form, text: e.target.value })}
          />
          <label className="text-xs text-slate-500">
            Authority
            <input
              type="number"
              step="0.1"
              min="0"
              max="1"
              className="border rounded px-2 py-1 w-20 ml-2 text-sm"
              value={form.authority}
              onChange={(e) => setForm({ ...form, authority: Number(e.target.value) })}
            />
          </label>
          <button
            onClick={() => ingest.mutate()}
            disabled={ingest.isPending || !form.title || !form.text}
            className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
          >
            Ingest
          </button>
        </div>
      </Card>

      <Card title="Search (hybrid retrieval)" className="lg:col-span-2">
        <div className="flex gap-2">
          <input
            className="flex-1 border rounded px-2 py-1 text-sm"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Try: refund policy for annual plans"
          />
          <button
            onClick={() => search.refetch()}
            className="bg-slate-800 text-white px-3 py-1.5 rounded text-sm"
          >
            Search
          </button>
        </div>
        <div className="mt-3 space-y-2">
          {search.data?.map((r: any) => (
            <div key={r.chunk_id} className="text-xs border-l-2 border-slate-200 pl-2">
              <div className="flex gap-2 text-slate-400">
                <span className="font-medium text-slate-600">{r.document_title}</span>
                <span>vec {r.vector_score}</span>
                <span>bm25 {r.keyword_score}</span>
                <span>rerank {r.rerank_score}</span>
              </div>
              {r.text.slice(0, 260)}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
