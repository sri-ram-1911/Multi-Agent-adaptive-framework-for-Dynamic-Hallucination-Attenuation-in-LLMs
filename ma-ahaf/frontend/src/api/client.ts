import type {
  GenerateResponse,
  MetricsSummary,
  TraceListItem,
} from "../lib/types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

function apiKey(): string {
  return localStorage.getItem("maahaf_api_key") || "dev-key";
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey(),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  generate: (body: {
    prompt: string;
    context?: string;
    policy_profile?: string;
    policy_overrides?: Record<string, number>;
  }) => req<GenerateResponse>("/v1/generate", { method: "POST", body: JSON.stringify(body) }),

  traces: (params: { limit?: number; action?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set("limit", String(params.limit));
    if (params.action) q.set("action", params.action);
    return req<TraceListItem[]>(`/v1/traces?${q}`);
  },

  trace: (id: string) => req<any>(`/v1/traces/${id}`),

  metrics: () => req<MetricsSummary>("/v1/metrics/summary"),

  escalations: () => req<any[]>("/v1/metrics/escalations"),

  kbDocuments: () => req<any[]>("/v1/kb/documents"),
  kbSearch: (query: string, k = 5) =>
    req<any[]>("/v1/kb/search", { method: "POST", body: JSON.stringify({ query, k }) }),
  kbIngest: (body: { title: string; source: string; text: string; authority?: number }) =>
    req<any>("/v1/kb/documents", { method: "POST", body: JSON.stringify(body) }),

  evalRuns: () => req<any[]>("/v1/eval/runs"),
  evalRun: (id: string) => req<any>(`/v1/eval/runs/${id}`),
  startEval: (limit = 20) =>
    req<any>(`/v1/eval/run?limit=${limit}`, { method: "POST" }),

  reviewQueue: (status = "pending") =>
    req<any[]>(`/v1/review/queue?status=${status}`),
  reviewStats: () => req<{ pending: number; reviewed: number }>("/v1/review/queue/stats"),
  reviewItem: (id: string) => req<any>(`/v1/review/queue/${id}`),
  resolveReview: (id: string, body: { decision: string; note?: string; revised_response?: string }) =>
    req<any>(`/v1/review/queue/${id}/resolve`, { method: "POST", body: JSON.stringify(body) }),

  graph: () => req<{ mermaid: string }>("/v1/graph"),
};

export { apiKey };
