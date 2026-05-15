import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export default function SyncReport() {
  const [view, setView] = useState<"daily" | "weekly">("daily");
  const daily = useQuery({ queryKey: ["sync-daily"], queryFn: () => api.sync.daily(), enabled: view === "daily" });
  const weekly = useQuery({ queryKey: ["sync-weekly"], queryFn: () => api.sync.weekly(), enabled: view === "weekly" });
  const isLoading = view === "daily" ? daily.isLoading : weekly.isLoading;

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-1">Sync Reports</h1>
      <p className="text-gray-600 text-sm mb-6">What agents did and what it cost.</p>
      <div className="flex gap-1 mb-6 bg-gray-900 rounded-lg p-1 w-fit">
        {(["daily", "weekly"] as const).map((v) => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
              view === v ? "bg-gray-700 text-white" : "text-gray-500 hover:text-gray-300"
            }`}>
            {v.charAt(0).toUpperCase() + v.slice(1)}
          </button>
        ))}
      </div>
      {isLoading && <div className="text-gray-600 text-sm">Loading...</div>}
      {view === "daily" && daily.data && (
        <div>
          <div className="grid grid-cols-4 gap-3 mb-6">
            {[
              { label: "Sessions", value: daily.data.sessions.length },
              { label: "Agent Runs", value: daily.data.runs.length },
              { label: "State Changes", value: daily.data.transitions.length },
              { label: "Total Cost", value: `$${daily.data.total_cost_usd.toFixed(4)}` },
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="text-2xl font-bold text-white">{value}</div>
                <div className="text-xs text-gray-600 mt-1">{label}</div>
              </div>
            ))}
          </div>
          {daily.data.runs.length > 0 ? (
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-600 mb-3">What Agents Did</h2>
              {daily.data.runs.map((r, i) => (
                <div key={i} className="flex gap-3 text-sm mb-2 items-start">
                  <span className="text-blue-500 font-mono text-xs shrink-0 mt-0.5">[{r.tool}]</span>
                  <span className="text-gray-400 shrink-0">{r.agent_name}</span>
                  <span className="text-gray-500">— {r.summary}</span>
                </div>
              ))}
            </div>
          ) : <p className="text-gray-700 text-sm">Nothing logged today yet.</p>}
        </div>
      )}
      {view === "weekly" && weekly.data && (
        <div>
          <div className="grid grid-cols-3 gap-3 mb-6">
            {[
              { label: "Total Runs", value: weekly.data.total_runs },
              { label: "Total Cost", value: `$${weekly.data.total_cost_usd.toFixed(4)}` },
              { label: "Period", value: `${weekly.data.period.from} → ${weekly.data.period.to}` },
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="text-xl font-bold text-white">{value}</div>
                <div className="text-xs text-gray-600 mt-1">{label}</div>
              </div>
            ))}
          </div>
          {weekly.data.days.filter((d) => d.runs.length > 0).length === 0 ? (
            <p className="text-gray-700 text-sm">No activity this week.</p>
          ) : weekly.data.days.filter((d) => d.runs.length > 0).map((d) => (
            <div key={d.date} className="mb-4 border-l-2 border-gray-800 pl-4">
              <div className="text-sm font-semibold text-gray-300 mb-1">
                {d.date}<span className="text-gray-600 font-normal ml-3">{d.runs.length} runs · ${d.total_cost_usd.toFixed(4)}</span>
              </div>
              {d.runs.map((r, i) => (
                <div key={i} className="text-xs text-gray-600">[{r.tool}] {r.agent_name}: {r.summary}</div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
