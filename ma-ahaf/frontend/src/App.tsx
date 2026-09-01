import { NavLink, Route, Routes } from "react-router-dom";
import { apiKey } from "./api/client";
import { Evaluation } from "./pages/Evaluation";
import { KnowledgeBase } from "./pages/KnowledgeBase";
import { Metrics } from "./pages/Metrics";
import { Playground } from "./pages/Playground";
import { TraceDetail } from "./pages/TraceDetail";
import { Traces } from "./pages/Traces";

const NAV = [
  ["/", "Playground"],
  ["/traces", "Traces"],
  ["/metrics", "Metrics"],
  ["/evaluation", "Evaluation"],
  ["/kb", "Knowledge Base"],
];

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="bg-ink text-white">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-6">
          <div className="font-bold tracking-tight">
            MA-AHAF <span className="text-slate-400 font-normal text-sm">adaptive reliability control</span>
          </div>
          <nav className="flex gap-1 text-sm">
            {NAV.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded ${isActive ? "bg-white/15" : "hover:bg-white/10"}`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <button
            className="ml-auto text-xs text-slate-300 hover:text-white"
            onClick={() => {
              const k = prompt("API key", apiKey());
              if (k) localStorage.setItem("maahaf_api_key", k);
            }}
          >
            API key: {apiKey().slice(0, 6)}…
          </button>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-6 py-6">
        <Routes>
          <Route path="/" element={<Playground />} />
          <Route path="/traces" element={<Traces />} />
          <Route path="/traces/:id" element={<TraceDetail />} />
          <Route path="/metrics" element={<Metrics />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/kb" element={<KnowledgeBase />} />
        </Routes>
      </main>
    </div>
  );
}
