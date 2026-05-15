import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import ProjectList from "./components/ProjectList";
import KanbanBoard from "./components/KanbanBoard";
import TaskDetail from "./components/TaskDetail";
import ApprovalQueue from "./components/ApprovalQueue";
import SyncReport from "./components/SyncReport";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 5000 } } });

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <div className="flex h-screen bg-gray-950 text-gray-100" style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>
          <nav className="w-48 shrink-0 border-r border-gray-800 p-4 flex flex-col gap-1">
            <div className="text-base font-bold text-white mb-8 tracking-tight flex items-center gap-2">
              <span className="text-xl">⬛</span> Slate
            </div>
            {[
              { to: "/", label: "Projects", icon: "◈" },
              { to: "/approvals", label: "Approvals", icon: "◉" },
              { to: "/sync", label: "Sync", icon: "◎" },
            ].map(({ to, label, icon }) => (
              <NavLink
                key={to}
                to={to}
                end
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors ${
                    isActive ? "bg-gray-800 text-white" : "text-gray-500 hover:text-gray-200 hover:bg-gray-900"
                  }`
                }
              >
                <span className="text-xs">{icon}</span>
                {label}
              </NavLink>
            ))}
          </nav>
          <main className="flex-1 overflow-auto">
            <Routes>
              <Route path="/" element={<ProjectList />} />
              <Route path="/projects/:id" element={<KanbanBoard />} />
              <Route path="/tasks/:id" element={<TaskDetail />} />
              <Route path="/approvals" element={<ApprovalQueue />} />
              <Route path="/sync" element={<SyncReport />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
