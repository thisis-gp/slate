import aiosqlite

DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
    completed_at REAL,
    cost_usd REAL DEFAULT 0.0,
    wave_count INTEGER DEFAULT 0,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    role TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    wave INTEGER NOT NULL DEFAULT 1,
    assignment TEXT,
    output TEXT,
    cost_usd REAL DEFAULT 0.0,
    started_at REAL,
    completed_at REAL,
    confidence_score REAL,
    worktree_path TEXT
);

CREATE TABLE IF NOT EXISTS cost_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT REFERENCES agents(id),
    task_id TEXT REFERENCES tasks(id),
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER DEFAULT 0,
    cost_usd REAL NOT NULL,
    ts REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_agent TEXT NOT NULL,
    to_agent TEXT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    type TEXT NOT NULL,
    body TEXT NOT NULL,
    ts REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
    read INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    agent_id TEXT,
    task_id TEXT,
    payload TEXT NOT NULL,
    hash TEXT NOT NULL,
    ts REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS reflexion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT REFERENCES tasks(id),
    role TEXT NOT NULL,
    attempted TEXT NOT NULL,
    failed_because TEXT NOT NULL,
    correct_approach TEXT NOT NULL,
    ts REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE INDEX IF NOT EXISTS idx_agents_task ON agents(task_id);
CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id);
CREATE INDEX IF NOT EXISTS idx_cost_task ON cost_events(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
"""

async def apply_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript(DDL)
    await conn.commit()
