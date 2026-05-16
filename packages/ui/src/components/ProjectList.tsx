import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function ProjectList() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: api.projects.list,
  });
  const create = useMutation({
    mutationFn: () => api.projects.create(name.trim(), "", key.trim().toUpperCase()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["projects"] }); setName(""); setKey(""); },
  });

  const handleCreate = () => {
    if (name.trim()) create.mutate();
  };

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-1">Projects</h1>
      <p className="text-gray-500 text-sm mb-6">Your work lives here.</p>
      <div className="flex gap-2 mb-8">
        <input
          value={key}
          onChange={(e) => setKey(e.target.value.toUpperCase().slice(0, 6))}
          placeholder="KEY"
          className="w-20 bg-gray-900 border border-gray-800 rounded px-3 py-2 text-sm focus:outline-none focus:border-gray-600 placeholder-gray-700 font-mono uppercase"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && name.trim() && handleCreate()}
          placeholder="New project name — press Enter"
          className="flex-1 bg-gray-900 border border-gray-800 rounded px-3 py-2 text-sm focus:outline-none focus:border-gray-600 placeholder-gray-700"
        />
        <button
          onClick={handleCreate}
          disabled={create.isPending}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm font-medium transition-colors"
        >
          {create.isPending ? "..." : "Create"}
        </button>
      </div>
      {isLoading && <div className="text-gray-600 text-sm">Loading...</div>}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {projects.map((p) => (
          <button
            key={p.id}
            onClick={() => nav(`/projects/${p.id}`)}
            className="text-left border border-gray-800 hover:border-gray-600 rounded-lg p-4 bg-gray-900 hover:bg-gray-800 transition-colors"
          >
            <div className="flex items-center gap-2 mb-1">
              <div className="font-semibold text-white text-sm">{p.name}</div>
              {p.key && (
                <span className="text-xs font-mono bg-blue-900/50 text-blue-300 px-1.5 py-0.5 rounded">
                  {p.key}
                </span>
              )}
            </div>
            {p.description && <div className="text-gray-500 text-xs mt-1 line-clamp-2">{p.description}</div>}
            <div className="text-gray-700 text-xs mt-3 font-mono">{p.id.slice(0, 8)}</div>
          </button>
        ))}
        {!isLoading && projects.length === 0 && (
          <div className="col-span-3 text-center text-gray-700 py-16 text-sm">No projects yet.</div>
        )}
      </div>
    </div>
  );
}
