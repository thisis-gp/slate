import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type DailySync } from "../api/client";

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  );
}

function DailyDetail({ data }: { data: DailySync }) {
  const taskMap: Record<string, { title: string; runs: typeof data.runs; transitions: typeof data.transitions }> = {};

  for (const r of data.runs) {
    if (!taskMap[r.task_id]) taskMap[r.task_id] = { title: r.task_title || r.task_id.slice(0, 8), runs: [], transitions: [] };
    taskMap[r.task_id].runs.push(r);
  }
  for (const t of data.transitions) {
    if (!taskMap[t.task_id]) taskMap[t.task_id] = { title: t.task_title || t.task_id.slice(0, 8), runs: [], transitions: [] };
    taskMap[t.task_id].transitions.push(t);
  }

  const tasks = Object.entries(taskMap);

  if (tasks.length === 0) {
    return <p className="text-gray-600 text-sm mt-4">No task activity logged today.</p>;
  }

  return (
    <div className="mt-6 space-y-4">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Tasks Worked On</h2>
      {tasks.map(([tid, task]) => {
        const taskCost = task.runs.reduce((s, r) => s + (r.cost_usd ?? 0), 0);
        const finalState = task.transitions[task.transitions.length - 1]?.to_state;
        return (
          <div key={tid} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex items-start justify-between mb-3">
              <div>
                <span className="font-medium text-white">{task.title}</span>
                {finalState && (
                  <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-gray-800 text-cyan-400">{finalState}</span>
                )}
              </div>
              {taskCost > 0 && (
                <span className="text-yellow-400 text-sm font-mono">${taskCost.toFixed(4)}</span>
              )}
            </div>

            {task.transitions.length > 0 && (
              <div className="mb-2">
                <div className="text-xs text-gray-500 mb-1">State changes</div>
                <div className="flex flex-wrap gap-1">
                  {task.transitions.map((t, i) => (
                    <span key={i} className="text-xs text-gray-400">
                      {t.from_state || "-"} <span className="text-gray-600">→</span> <span className="text-cyan-400">{t.to_state}</span>
                      <span className="text-gray-600 ml-1">by {t.changed_by}</span>
                      {i < task.transitions.length - 1 && <span className="text-gray-700 mx-1">·</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {task.runs.length > 0 && (
              <div>
                <div className="text-xs text-gray-500 mb-1">Agent runs</div>
                <div className="space-y-1">
                  {task.runs.map((r, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="text-blue-400 font-mono shrink-0">[{r.tool}]</span>
                      <span className="text-gray-400 shrink-0">{r.agent_name}</span>
                      <span className="text-gray-500 flex-1">{r.summary}</span>
                      {r.cost_usd > 0 && <span className="text-yellow-500 font-mono shrink-0">${r.cost_usd.toFixed(4)}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function SyncReport() {
  const [view, setView] = useState<"daily" | "weekly">("daily");
  const daily = useQuery({ queryKey: ["sync-daily"], queryFn: () => api.sync.daily(), enabled: view === "daily" });
  const weekly = useQuery({ queryKey: ["sync-weekly"], queryFn: () => api.sync.weekly(), enabled: view === "weekly" });
  const isLoading = view === "daily" ? daily.isLoading : weekly.isLoading;

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-1">Sync Reports</h1>
      <p className="text-gray-500 text-sm mb-6">What agents did, which tasks moved, and what it cost.</p>

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
          <div className="grid grid-cols-4 gap-3 mb-2">
            <StatCard label="Sessions" value={daily.data.sessions.length} />
            <StatCard label="Agent Runs" value={daily.data.runs.length} />
            <StatCard label="State Changes" value={daily.data.transitions.length} />
            <StatCard label="Total Cost" value={`$${daily.data.total_cost_usd.toFixed(4)}`} />
          </div>
          <DailyDetail data={daily.data} />
        </div>
      )}

      {view === "weekly" && weekly.data && (
        <div>
          <div className="grid grid-cols-3 gap-3 mb-6">
            <StatCard label="Total Runs" value={weekly.data.total_runs} />
            <StatCard label="Total Cost" value={`$${weekly.data.total_cost_usd.toFixed(4)}`} />
            <StatCard label="Period" value={`${weekly.data.period.from} – ${weekly.data.period.to}`} />
          </div>

          {weekly.data.days.filter((d) => d.transitions.length > 0 || d.runs.length > 0).length === 0 ? (
            <p className="text-gray-600 text-sm">No activity this week.</p>
          ) : (
            weekly.data.days
              .filter((d) => d.transitions.length > 0 || d.runs.length > 0)
              .map((d) => (
                <div key={d.date} className="mb-6">
                  <div className="flex items-center gap-3 mb-3 border-b border-gray-800 pb-2">
                    <span className="font-semibold text-white">{d.date}</span>
                    <span className="text-xs text-gray-500">{d.runs.length} runs</span>
                    <span className="text-xs text-gray-500">{d.transitions.length} transitions</span>
                    {d.total_cost_usd > 0 && (
                      <span className="text-xs text-yellow-500 font-mono">${d.total_cost_usd.toFixed(4)}</span>
                    )}
                  </div>
                  <DailyDetail data={d} />
                </div>
              ))
          )}
        </div>
      )}
    </div>
  );
}
