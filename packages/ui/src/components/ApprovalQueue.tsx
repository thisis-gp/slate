import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export default function ApprovalQueue() {
  const qc = useQueryClient();
  const { data: approvals = [], isLoading } = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api.approvals.list("pending"),
    refetchInterval: 8000,
  });
  const respond = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "approved" | "rejected" }) =>
      api.approvals.respond(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-1">Approvals</h1>
      <p className="text-gray-600 text-sm mb-6">Agents waiting for your decision. Refreshes every 8s.</p>
      {isLoading && <div className="text-gray-600 text-sm">Loading...</div>}
      {!isLoading && approvals.length === 0 && (
        <div className="text-center text-gray-700 py-16 text-sm">No pending approvals.</div>
      )}
      <div className="space-y-3">
        {approvals.map((a) => (
          <div key={a.id} className="border border-yellow-900/60 bg-yellow-950/20 rounded-lg p-5">
            <div className="flex justify-between items-start gap-4">
              <div className="flex-1">
                <div className="text-xs text-yellow-600 font-semibold mb-1">{a.requested_by} requesting approval</div>
                <div className="text-white text-sm leading-relaxed">{a.reason}</div>
                {a.task_id && <div className="text-xs text-gray-600 mt-2 font-mono">task/{a.task_id.slice(0, 8)}</div>}
              </div>
              <div className="flex gap-2 shrink-0">
                <button onClick={() => respond.mutate({ id: a.id, status: "approved" })}
                  disabled={respond.isPending}
                  className="px-3 py-1.5 bg-green-800 hover:bg-green-700 disabled:opacity-50 rounded text-sm font-medium transition-colors">
                  Approve
                </button>
                <button onClick={() => respond.mutate({ id: a.id, status: "rejected" })}
                  disabled={respond.isPending}
                  className="px-3 py-1.5 bg-red-900 hover:bg-red-800 disabled:opacity-50 rounded text-sm font-medium transition-colors">
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
