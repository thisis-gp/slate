import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type PendingResponse, type PendingIssue } from "../api/client";

function hm(seconds: number): string {
  const m = Math.max(1, Math.round(seconds / 60));
  const h = Math.floor(m / 60);
  const r = m % 60;
  return h > 0 ? `${h}h ${r}m` : `${r}m`;
}

function providerBadge(p?: string) {
  if (!p) return null;
  const color: Record<string, string> = {
    moonshot: "text-fuchsia-400", nvidia: "text-green-400",
    gemini: "text-blue-400", concat: "text-gray-500",
  };
  const label = p === "moonshot" ? "kimi" : p;
  return <span className={`text-[10px] uppercase tracking-wider ${color[p] ?? "text-gray-500"}`}>{label}</span>;
}

function getBatch(d?: PendingResponse): PendingIssue[] | null {
  const issues = d?.batch?.issues;
  return issues && issues.length ? issues : null;
}
function getId(d?: PendingResponse): string | undefined {
  return d?.id ?? d?.pending_id ?? undefined;
}

function IssueCard({ issue, excluded, onToggle }: { issue: PendingIssue; excluded: boolean; onToggle: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`bg-gray-900 border rounded-lg p-4 ${excluded ? "border-gray-800 opacity-50" : "border-gray-700"}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="font-bold text-white">{issue.jira_key}</span>
          {providerBadge(issue.summary_provider)}
          <span className="text-[11px] text-gray-600 font-mono">{issue.task_id?.slice(0, 8)}</span>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
          <input type="checkbox" checked={!excluded} onChange={onToggle} /> include
        </label>
      </div>

      <div className="mb-2 text-sm">
        <span className="text-xs text-gray-500 mr-2 uppercase tracking-wider">Status</span>
        {issue.target_status ? (
          <span className="text-gray-300">
            {issue.current_state || "-"} <span className="text-gray-600">→</span>{" "}
            <span className="text-cyan-400">{issue.target_status}</span>
          </span>
        ) : (
          <span className="text-gray-600">no change</span>
        )}
      </div>

      <div className="text-sm">
        <span className="text-xs text-gray-500 mr-2 uppercase tracking-wider">Worklog</span>
        <span className="text-yellow-400 font-mono">{hm(issue.total_seconds)}</span>
        <span className="text-gray-600 ml-2">
          {issue.entries.length} run{issue.entries.length === 1 ? "" : "s"}
        </span>
        <div className="mt-1 whitespace-pre-wrap text-gray-300 bg-gray-950 border border-gray-800 rounded p-2 text-xs">
          {issue.summary || "(no summary)"}
        </div>
        {issue.entries.length > 0 && (
          <button onClick={() => setOpen(!open)} className="text-[11px] text-gray-500 hover:text-gray-300 mt-1">
            {open ? "▾ hide" : "▸ show"} raw run notes
          </button>
        )}
        {open && (
          <ul className="mt-1 space-y-0.5">
            {issue.entries.map((e, i) => (
              <li key={i} className="text-[11px] text-gray-500">• {e}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function JiraSync() {
  const qc = useQueryClient();
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [result, setResult] = useState("");

  const pending = useQuery({ queryKey: ["jira-pending"], queryFn: () => api.jira.pending() });
  const data = pending.data;
  const issues = getBatch(data);
  const id = getId(data);

  const preview = useMutation({
    mutationFn: () => api.jira.preview(),
    onSuccess: () => { setResult(""); setExcluded(new Set()); qc.invalidateQueries({ queryKey: ["jira-pending"] }); },
  });
  const approve = useMutation({
    mutationFn: () => api.jira.approve(id!, Array.from(excluded)),
    onSuccess: (r) => { setResult(`Pushed ${r.pushed}, failed ${r.failed}.`); qc.invalidateQueries({ queryKey: ["jira-pending"] }); },
  });
  const reject = useMutation({
    mutationFn: () => api.jira.reject(id!),
    onSuccess: () => { setResult("Rejected — nothing pushed."); qc.invalidateQueries({ queryKey: ["jira-pending"] }); },
  });

  const toggle = (k: string) =>
    setExcluded((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const included = issues ? issues.filter((i) => !excluded.has(i.jira_key)) : [];
  const totalSecs = included.reduce((s, i) => s + i.total_seconds, 0);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-1">Jira Sync — Approval</h1>

      {data?.unlinked_count != null && data.unlinked_count > 0 && (
        <div className="mb-4 rounded-lg border border-amber-400/40 bg-amber-900/30 px-4 py-2 text-sm text-amber-300">
          ⚠ {data.unlinked_count} worklog(s) pending a Jira key — link the task to a BX-&lt;number&gt; issue so they sync.
        </div>
      )}

      <p className="text-gray-500 text-sm mb-6">
        Review what slate will push to Jira — status transitions and one summarized worklog per issue.
        Nothing is pushed until you approve.
      </p>

      <div className="flex gap-2 mb-6">
        <button onClick={() => preview.mutate()} disabled={preview.isPending}
          className="px-4 py-1.5 rounded text-sm bg-gray-800 text-gray-200 hover:bg-gray-700 disabled:opacity-40">
          {preview.isPending ? "Staging…" : "Stage / refresh batch"}
        </button>
      </div>

      {result && <div className="mb-4 text-sm text-cyan-400">{result}</div>}
      {pending.isLoading && <div className="text-gray-600 text-sm">Loading…</div>}

      {!issues && !pending.isLoading && (
        <p className="text-gray-600 text-sm">
          No pending batch. Click <span className="text-gray-300">Stage / refresh batch</span> to build today's
          sync from unsynced worklogs.
        </p>
      )}

      {issues && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-2xl font-bold text-white">{included.length}/{issues.length}</div>
              <div className="text-xs text-gray-500 mt-1">Issues to push</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-2xl font-bold text-yellow-400">{hm(totalSecs)}</div>
              <div className="text-xs text-gray-500 mt-1">Total time</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="text-2xl font-bold text-white">{data?.summary_provider ?? "—"}</div>
              <div className="text-xs text-gray-500 mt-1">Summarizer</div>
            </div>
          </div>

          <div className="space-y-3 mb-6">
            {issues.map((i) => (
              <IssueCard key={i.jira_key} issue={i} excluded={excluded.has(i.jira_key)} onToggle={() => toggle(i.jira_key)} />
            ))}
          </div>

          <div className="flex gap-2">
            <button onClick={() => approve.mutate()} disabled={!id || approve.isPending || included.length === 0}
              className="px-5 py-2 rounded text-sm font-medium bg-emerald-700 text-white hover:bg-emerald-600 disabled:opacity-40">
              {approve.isPending ? "Pushing…" : `Approve & push ${included.length} issue${included.length === 1 ? "" : "s"}`}
            </button>
            <button onClick={() => reject.mutate()} disabled={!id || reject.isPending}
              className="px-5 py-2 rounded text-sm font-medium bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40">
              Reject
            </button>
          </div>
        </>
      )}
    </div>
  );
}
