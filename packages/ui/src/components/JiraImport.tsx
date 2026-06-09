import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type PendingImport } from "../api/client";

function priorityColor(p?: string): string {
  switch ((p || "").toLowerCase()) {
    case "highest":
    case "critical": return "text-red-400";
    case "high": return "text-orange-400";
    case "low":
    case "lowest": return "text-gray-500";
    default: return "text-gray-400";
  }
}

function ImportRow({ row }: { row: PendingImport }) {
  const qc = useQueryClient();
  const [project, setProject] = useState("");
  const [assign, setAssign] = useState("");
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api.projects.list() });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["jira-imports"] });
    qc.invalidateQueries({ queryKey: ["projects"] });
  };
  const approve = useMutation({
    mutationFn: () => api.jira.approveImport(row.id, project, assign),
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: () => api.jira.rejectImport(row.id),
    onSuccess: invalidate,
  });

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="font-bold text-white">{row.jira_key}</span>
          {row.issue_type && (
            <span className="text-[10px] uppercase tracking-wider text-cyan-400">{row.issue_type}</span>
          )}
          {row.priority && (
            <span className={`text-[10px] uppercase tracking-wider ${priorityColor(row.priority)}`}>
              {row.priority}
            </span>
          )}
          {row.jira_status && <span className="text-[11px] text-gray-600">{row.jira_status}</span>}
        </div>
      </div>

      <div className="text-sm text-gray-300 mb-3">{row.summary || "(no summary)"}</div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-gray-500">Project</span>
          <select
            value={project}
            onChange={(e) => setProject(e.target.value)}
            className="bg-gray-950 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 min-w-[12rem]"
          >
            <option value="">— pick a project —</option>
            {projects.data?.map((p) => (
              <option key={p.id} value={p.id}>{p.key ? `${p.key} · ` : ""}{p.name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-gray-500">Assign (optional)</span>
          <input
            value={assign}
            onChange={(e) => setAssign(e.target.value)}
            placeholder="me"
            className="bg-gray-950 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 w-28"
          />
        </label>
        <button
          onClick={() => approve.mutate()}
          disabled={!project || approve.isPending}
          className="px-4 py-1.5 rounded text-sm font-medium bg-emerald-700 text-white hover:bg-emerald-600 disabled:opacity-40"
        >
          {approve.isPending ? "Importing…" : "Approve & import"}
        </button>
        <button
          onClick={() => reject.mutate()}
          disabled={reject.isPending}
          className="px-4 py-1.5 rounded text-sm bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40"
        >
          Reject
        </button>
        {approve.isError && <span className="text-xs text-red-400">{(approve.error as Error).message}</span>}
      </div>
    </div>
  );
}

export default function JiraImport() {
  const qc = useQueryClient();
  const [note, setNote] = useState("");

  const imports = useQuery({ queryKey: ["jira-imports"], queryFn: () => api.jira.imports() });
  const rows = imports.data ?? [];

  const stage = useMutation({
    mutationFn: () => api.jira.stageImports(),
    onSuccess: (r) => {
      if (typeof r.skipped === "boolean" && r.skipped) {
        setNote(r.reason || "Jira not configured.");
      } else {
        const skippedCount = Array.isArray(r.skipped) ? r.skipped.length : 0;
        setNote(`Staged ${r.staged_count ?? 0} new from ${r.fetched ?? 0} fetched (${skippedCount} skipped).`);
      }
      qc.invalidateQueries({ queryKey: ["jira-imports"] });
    },
  });

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-1">Jira Import — Approval</h1>
      <p className="text-gray-500 text-sm mb-6">
        Pull issues assigned to you from Jira. Nothing becomes a Slate task until you pick a
        project and approve it here.
      </p>

      <div className="flex gap-2 mb-6">
        <button
          onClick={() => stage.mutate()}
          disabled={stage.isPending}
          className="px-4 py-1.5 rounded text-sm bg-gray-800 text-gray-200 hover:bg-gray-700 disabled:opacity-40"
        >
          {stage.isPending ? "Fetching…" : "Fetch assigned issues"}
        </button>
      </div>

      {note && <div className="mb-4 text-sm text-cyan-400">{note}</div>}
      {imports.isLoading && <div className="text-gray-600 text-sm">Loading…</div>}

      {!imports.isLoading && rows.length === 0 && (
        <p className="text-gray-600 text-sm">
          No issues awaiting import. Click <span className="text-gray-300">Fetch assigned issues</span> to
          stage what's assigned to you in Jira.
        </p>
      )}

      {rows.length > 0 && (
        <>
          <div className="text-xs text-gray-500 mb-3">{rows.length} issue(s) awaiting your decision</div>
          <div className="space-y-3">
            {rows.map((r) => <ImportRow key={r.id} row={r} />)}
          </div>
        </>
      )}
    </div>
  );
}
