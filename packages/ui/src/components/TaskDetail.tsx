import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";

const STATES = ["todo","investigating","implementing","code_review","qa","ready_to_merge","done","blocked","cancelled"];
const STATUS_STYLES: Record<string, string> = {
  completed: "bg-green-900/50 text-green-400",
  failed: "bg-red-900/50 text-red-400",
  blocked: "bg-yellow-900/50 text-yellow-400",
  in_progress: "bg-blue-900/50 text-blue-400",
};

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data: ctx, isLoading } = useQuery({
    queryKey: ["task-context", id],
    queryFn: () => api.tasks.context(id!),
    refetchInterval: 10000,
  });
  const move = useMutation({
    mutationFn: (state: string) => api.tasks.move(id!, state),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task-context", id] }),
  });

  if (isLoading || !ctx) return <div className="p-8 text-gray-600 text-sm">Loading...</div>;
  const { task, runs, transitions } = ctx;
  const totalCost = runs.reduce((s, r) => s + r.cost_usd, 0);

  return (
    <div className="p-8 max-w-2xl">
      <button onClick={() => nav(-1)} className="text-gray-500 hover:text-white text-sm mb-6 block transition-colors">← Back</button>
      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex-1">
          <div className="text-xs text-gray-600 font-mono mb-1">{task.id.slice(0, 8)}</div>
          <h1 className="text-xl font-bold text-white leading-snug">{task.title}</h1>
          <div className="flex gap-2 mt-2 flex-wrap">
            <span className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded">{task.type}</span>
            <span className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded">{task.priority}</span>
            {task.assigned_to && <span className="text-xs bg-blue-900/50 text-blue-400 px-2 py-1 rounded">{task.assigned_to}</span>}
            {totalCost > 0 && <span className="text-xs bg-gray-800 text-yellow-600 px-2 py-1 rounded">${totalCost.toFixed(4)}</span>}
          </div>
        </div>
        <select value={task.state} onChange={(e) => move.mutate(e.target.value)}
          className="shrink-0 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-gray-500">
          {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {task.description && <p className="text-gray-400 text-sm mb-6 leading-relaxed">{task.description}</p>}
      <section className="mb-8">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-600 mb-3">
          Agent Runs <span className="text-gray-700 font-normal">({runs.length})</span>
        </h2>
        {runs.length === 0 ? <p className="text-gray-700 text-sm">No agent runs yet.</p> : runs.map((r) => (
          <div key={r.id} className="border-l-2 border-gray-800 hover:border-blue-800 pl-4 mb-5 transition-colors">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-xs font-semibold text-blue-400">{r.agent_name}</span>
              <span className="text-xs bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded">{r.tool}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_STYLES[r.status] ?? "bg-gray-800 text-gray-400"}`}>{r.status}</span>
              {r.cost_usd > 0 && <span className="text-xs text-gray-600">${r.cost_usd.toFixed(4)}</span>}
            </div>
            <p className="text-sm text-gray-300">{r.summary}</p>
            {r.outcome && <p className="text-xs text-gray-500 mt-1 italic">{r.outcome}</p>}
          </div>
        ))}
      </section>
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-600 mb-3">State History</h2>
        <div className="space-y-1">
          {transitions.map((t, i) => (
            <div key={i} className="flex gap-3 items-center text-xs">
              <span className="text-gray-500">{t.from_state ?? "—"}</span>
              <span className="text-gray-700">→</span>
              <span className="text-gray-200 font-medium">{t.to_state}</span>
              <span className="text-gray-600">by {t.changed_by}</span>
              {t.reason && <span className="text-gray-700 italic">{t.reason}</span>}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
