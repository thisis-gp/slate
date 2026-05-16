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
  id: string; name: string; key?: string; description?: string;
  status: string; created_at: number;
}
export interface Task {
  id: string; project_id: string; number?: number; title: string;
  state: string; priority: string; type: string;
  assigned_to?: string; reporter?: string; created_by: string;
  description?: string; parent_task_id?: string;
  story_points?: number; labels?: string; links?: string;
}
export interface Comment {
  id: number; task_id: string; author: string;
  author_type: string; body: string; ts: number;
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
    get: (id: string) => req<Project>(`/projects/${id}`),
    create: (name: string, description = "", key = "") =>
      req<Project>("/projects", { method: "POST", body: JSON.stringify({ name, description, key }) }),
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
      reporter?: string; story_points?: number; labels?: string; links?: string;
    }) => req<Task>("/tasks", { method: "POST", body: JSON.stringify(data) }),
    context: (id: string) => req<TaskContext>(`/tasks/${id}/context`),
    move: (id: string, to_state: string, changed_by = "human", new_assignee = "") =>
      req<Task>(`/tasks/${id}/move`, {
        method: "POST",
        body: JSON.stringify({ to_state, changed_by, new_assignee }),
      }),
  },
  comments: {
    list: (taskId: string) => req<Comment[]>(`/tasks/${taskId}/comments`),
    add: (taskId: string, author: string, body: string, author_type = "human") =>
      req<Comment>(`/tasks/${taskId}/comments`, {
        method: "POST",
        body: JSON.stringify({ author, body, author_type }),
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
