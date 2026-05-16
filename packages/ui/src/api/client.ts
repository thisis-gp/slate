const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:7331";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export interface Project {
  id: string; name: string; description?: string; status: string; created_at: number;
}
export interface Task {
  id: string; project_id: string; title: string; state: string; priority: string;
  type: string; assigned_to?: string; created_by: string; description?: string;
  parent_task_id?: string;
}
export interface AgentRun {
  id: string; task_id: string; agent_name: string; tool: string; summary: string;
  outcome?: string; status: string; cost_usd: number; started_at: number;
}
export interface StateTransition {
  id: number; task_id: string; from_state?: string; to_state: string;
  changed_by: string; reason?: string; ts: number;
}
export interface TaskContext {
  task: Task; runs: AgentRun[]; transitions: StateTransition[]; comments: unknown[];
}
export interface Approval {
  id: string; task_id?: string; requested_by: string; reason: string;
  status: string; response_note?: string; requested_at: number;
}
export interface DailySync {
  date: string; sessions: unknown[]; runs: RunEntry[]; transitions: TransitionEntry[];
  total_cost_usd: number;
}
export interface RunEntry {
  task_id: string; tool: string; agent_name: string; task_title: string;
  summary: string; cost_usd: number;
}
export interface TransitionEntry {
  task_id: string; task_title: string; from_state?: string; to_state: string;
  changed_by: string; reason?: string;
}
export interface WeeklySync {
  period: { from: string; to: string }; total_runs: number;
  total_cost_usd: number; days: DailySync[];
}

export const api = {
  projects: {
    list: () => req<Project[]>("/projects"),
    create: (name: string, description = "") =>
      req<Project>("/projects", { method: "POST", body: JSON.stringify({ name, description }) }),
  },
  tasks: {
    list: (params: { project_id?: string; state?: string; assigned_to?: string } = {}) => {
      const qs = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v)) as Record<string, string>
      ).toString();
      return req<Task[]>(`/tasks${qs ? `?${qs}` : ""}`);
    },
    create: (data: {
      project_id: string; title: string; description?: string; type?: string;
      priority?: string; created_by?: string; assigned_to?: string;
    }) => req<Task>("/tasks", { method: "POST", body: JSON.stringify(data) }),
    context: (id: string) => req<TaskContext>(`/tasks/${id}/context`),
    move: (id: string, to_state: string, changed_by = "human") =>
      req<Task>(`/tasks/${id}/move`, {
        method: "POST", body: JSON.stringify({ to_state, changed_by }),
      }),
  },
  approvals: {
    list: (status = "pending") => req<Approval[]>(`/approvals?status=${status}`),
    respond: (id: string, status: "approved" | "rejected", note = "") =>
      req(`/approvals/${id}/respond`, {
        method: "POST", body: JSON.stringify({ status, response_note: note }),
      }),
  },
  sync: {
    daily: (date_str = "") =>
      req<DailySync>(`/sync/daily${date_str ? `?date_str=${date_str}` : ""}`),
    weekly: () => req<WeeklySync>("/sync/weekly"),
  },
};
