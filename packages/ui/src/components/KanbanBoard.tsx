import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { api, Task } from "../api/client";

const COLUMNS = [
  { state: "todo",           label: "Todo",           color: "border-gray-600" },
  { state: "in_progress",    label: "In Progress",    color: "border-blue-700" },
  { state: "code_review",    label: "Code Review",    color: "border-purple-700" },
  { state: "qa",             label: "QA",             color: "border-orange-700" },
  { state: "ready_to_merge", label: "Ready",          color: "border-green-700" },
  { state: "done",           label: "Done",           color: "border-green-900" },
  { state: "blocked",        label: "Blocked",        color: "border-red-700" },
  { state: "on_hold",        label: "On Hold",        color: "border-yellow-700" },
  { state: "cancelled",      label: "Cancelled",      color: "border-gray-700" },
];

const PRIORITY_STYLES: Record<string, string> = {
  critical: "bg-red-900/50 text-red-400",
  high: "bg-orange-900/50 text-orange-400",
  medium: "bg-yellow-900/50 text-yellow-500",
  low: "bg-gray-800 text-gray-500",
};

function NewTaskForm({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [type, setType] = useState("feature");
  const [priority, setPriority] = useState("medium");
  const [points, setPoints] = useState(0);
  const [labels, setLabels] = useState("");
  const create = useMutation({
    mutationFn: () => api.tasks.create({
      project_id: projectId,
      title,
      type,
      priority,
      created_by: "human",
      story_points: points || undefined,
      labels: labels ? JSON.stringify(labels.split(",").map(l => l.trim()).filter(Boolean)) : undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["tasks", projectId] }); onClose(); },
  });
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h2 className="font-bold mb-4">New Task</h2>
        <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="Task title"
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mb-3 focus:outline-none focus:border-gray-500" />
        <div className="flex gap-2 mb-3">
          <select value={type} onChange={(e) => setType(e.target.value)}
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-2 text-sm">
            {["feature","bug","research","chore","spike"].map(t => <option key={t}>{t}</option>)}
          </select>
          <select value={priority} onChange={(e) => setPriority(e.target.value)}
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-2 text-sm">
            {["low","medium","high","critical"].map(p => <option key={p}>{p}</option>)}
          </select>
          <select value={points} onChange={(e) => setPoints(Number(e.target.value))}
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-2 text-sm">
            <option value={0}>- pts</option>
            {[1,2,3,5,8,13].map(p => <option key={p} value={p}>{p}pt</option>)}
          </select>
        </div>
        <input value={labels} onChange={(e) => setLabels(e.target.value)}
          placeholder="labels (comma-separated)"
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm mb-3 focus:outline-none focus:border-gray-500" />
        <div className="flex gap-2">
          <button onClick={() => title && create.mutate()}
            className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium">
            {create.isPending ? "Creating..." : "Create Task"}
          </button>
          <button onClick={onClose} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm">Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function KanbanBoard() {
  const { id: projectId } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [showNew, setShowNew] = useState(false);
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.projects.get(projectId!),
    enabled: !!projectId,
  });
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["tasks", projectId],
    queryFn: () => api.tasks.list({ project_id: projectId }),
    refetchInterval: 15000,
  });
  const byState = COLUMNS.reduce((acc, col) => {
    acc[col.state] = tasks.filter((t) => t.state === col.state);
    return acc;
  }, {} as Record<string, Task[]>);

  return (
    <div className="p-6 h-full flex flex-col">
      {showNew && projectId && <NewTaskForm projectId={projectId} onClose={() => setShowNew(false)} />}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <button onClick={() => nav("/")} className="text-gray-500 hover:text-white text-sm transition-colors">← Projects</button>
          <span className="text-gray-700">/</span>
          <span className="text-sm text-gray-400 font-mono">{project?.key ?? projectId?.slice(0, 8)}</span>
        </div>
        <button onClick={() => setShowNew(true)}
          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors">
          + New Task
        </button>
      </div>
      {isLoading && <div className="text-gray-600 text-sm">Loading tasks...</div>}
      <div className="flex gap-3 overflow-x-auto pb-4 flex-1">
        {COLUMNS.map(({ state, label, color }) => (
          <div key={state} className="shrink-0 w-60">
            <div className={`flex items-center justify-between text-xs font-semibold uppercase tracking-wider mb-3 pb-2 border-b ${color}`}>
              <span>{label}</span>
              <span className="text-gray-600 font-normal">{byState[state]?.length ?? 0}</span>
            </div>
            <div className="flex flex-col gap-2">
              {byState[state]?.map((t) => (
                <button key={t.id} onClick={() => nav(`/tasks/${t.id}`)}
                  className="text-left bg-gray-900 border border-gray-800 hover:border-gray-600 rounded p-3 transition-colors">
                  <div className="text-xs text-gray-600 font-mono mb-1">
                    {project?.key && t.number ? `${project.key}-${t.number}` : t.id.slice(0, 8)}
                  </div>
                  <div className="text-sm text-white mb-2 leading-snug">{t.title}</div>
                  <div className="flex flex-wrap gap-1">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${PRIORITY_STYLES[t.priority]}`}>{t.priority}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">{t.type}</span>
                    {t.assigned_to && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-blue-900/50 text-blue-400">{t.assigned_to}</span>
                    )}
                    {t.story_points && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">{t.story_points}pt</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
