export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-green-400 mb-2">Agentic OS</h1>
        <p className="text-gray-400">Agent dashboard coming in Phase 11</p>
        <p className="text-gray-600 text-sm mt-4">
          API running at{" "}
          <a href="http://localhost:7331/health" className="text-blue-400 underline">
            localhost:7331
          </a>
        </p>
      </div>
    </div>
  );
}
