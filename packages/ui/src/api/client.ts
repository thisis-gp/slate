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
  sprint_id?: string;
}
export interface Comment {
  id: number; task_id: string; author: string;
  author_type: string; body: string; ts: number;
}
export interface AgentRun {
  id: string; task_id: string; agent_name: string; tool: string; summary: string;
  outcome?: string; status: string; cost_usd: number; started_at: number;
  commit_sha?: string; commit_message?: string;
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
export interface Sprint {
  id: string; project_id: string; name: string;
  goal?: string; start_date?: string; end_date?: string;
  status: string; created_at: number;
}

export interface PendingIssue {
  jira_key: string; task_id: string;
  current_state?: string; target_status?: string;
  worklog_ids: string[]; entries: string[];
  total_seconds: number; started_ts: number;
  summary: string; summary_provider?: string;
}
export interface PendingBatch { issues: PendingIssue[] }
export interface PendingResponse {
  pending?: boolean | null;
  id?: string; pending_id?: string | null; status?: string;
  created_at?: number; summary_provider?: string;
  batch?: PendingBatch; reason?: string;
  unlinked_count?: number;
}
export interface JiraStatus {
  base_url?: string; email?: string; sync_time?: string; enabled?: boolean; state_map?: string;
}
export interface ApproveResult {
  pushed: number; failed: number;
  results: Array<{ jira_key: string; status: string; detail?: string }>;
  error?: string;
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
      sprint_id?: string;
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
  sync: {
    daily: (date_str = "") =>
      req<DailySync>(`/sync/daily${date_str ? `?date_str=${date_str}` : ""}`),
    weekly: () => req<WeeklySync>("/sync/weekly"),
  },
  sprints: {
    list: (params: { project_id?: string; status?: string } = {}) => {
      const qs = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v)) as Record<string, string>
      ).toString();
      return req<Sprint[]>(`/sprints${qs ? `?${qs}` : ""}`);
    },
    create: (data: { project_id: string; name: string; goal?: string; start_date?: string; end_date?: string }) =>
      req<Sprint>("/sprints", { method: "POST", body: JSON.stringify(data) }),
    get: (id: string) => req<Sprint & { tasks: unknown[] }>(`/sprints/${id}`),
    start: (id: string) => req<Sprint>(`/sprints/${id}/start`, { method: "POST" }),
    complete: (id: string) => req<Sprint>(`/sprints/${id}/complete`, { method: "POST" }),
    assign: (sprintId: string, taskId: string) =>
      req<{ ok: boolean }>(`/sprints/${sprintId}/assign/${taskId}`, { method: "POST" }),
  },
  jira: {
    status: () => req<JiraStatus>("/jira/status"),
    pending: () => req<PendingResponse>("/jira/pending"),
    preview: () => req<PendingResponse>("/jira/preview", { method: "POST" }),
    approve: (id: string, exclude: string[] = []) =>
      req<ApproveResult>(`/jira/pending/${id}/approve`, { method: "POST", body: JSON.stringify({ exclude }) }),
    reject: (id: string) => req<{ rejected: boolean }>(`/jira/pending/${id}/reject`, { method: "POST" }),
  },
};
