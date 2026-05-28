import aiosqlite

DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    key         TEXT UNIQUE,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
    updated_at  REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS sprints (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    name        TEXT NOT NULL,
    goal        TEXT,
    start_date  TEXT,
    end_date    TEXT,
    status      TEXT NOT NULL DEFAULT 'planning',
    created_at  REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id),
    parent_task_id TEXT REFERENCES tasks(id),
    sprint_id      TEXT REFERENCES sprints(id),
    number         INTEGER,
    title          TEXT NOT NULL,
    description    TEXT,
    type           TEXT NOT NULL DEFAULT 'feature',
    state          TEXT NOT NULL DEFAULT 'todo',
    priority       TEXT NOT NULL DEFAULT 'medium',
    created_by     TEXT NOT NULL DEFAULT 'human',
    reporter       TEXT,
    assigned_to    TEXT,
    story_points   INTEGER,
    labels         TEXT,
    links          TEXT,
    created_at     REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
    updated_at     REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS state_transitions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      TEXT NOT NULL REFERENCES tasks(id),
    from_state   TEXT,
    to_state     TEXT NOT NULL,
    changed_by   TEXT NOT NULL,
    new_assignee TEXT,
    reason       TEXT,
    ts           REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    agent_name    TEXT NOT NULL,
    tool          TEXT,
    project_id    TEXT REFERENCES projects(id),
    date          TEXT NOT NULL,
    started_at    REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
    ended_at      REAL,
    summary       TEXT,
    total_cost_usd REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id             TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL REFERENCES tasks(id),
    session_id     TEXT REFERENCES sessions(id),
    agent_name     TEXT NOT NULL,
    tool           TEXT NOT NULL,
    summary        TEXT NOT NULL,
    outcome        TEXT,
    status         TEXT NOT NULL DEFAULT 'completed',
    commit_sha     TEXT,
    commit_message TEXT,
    started_at     REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
    completed_at   REAL,
    cost_usd       REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS model_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_run_id      TEXT REFERENCES agent_runs(id),
    session_id        TEXT REFERENCES sessions(id),
    task_id           TEXT REFERENCES tasks(id),
    model             TEXT NOT NULL,
    provider          TEXT NOT NULL,
    input_tokens      INTEGER NOT NULL DEFAULT 0,
    output_tokens     INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL NOT NULL DEFAULT 0.0,
    ts                REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES tasks(id),
    author      TEXT NOT NULL,
    author_type TEXT NOT NULL DEFAULT 'human',
    body        TEXT NOT NULL,
    ts          REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE TABLE IF NOT EXISTS jira_config (
    id          INTEGER PRIMARY KEY DEFAULT 1,
    base_url    TEXT NOT NULL,
    email       TEXT NOT NULL,
    api_token   TEXT NOT NULL,
    sync_time   TEXT NOT NULL DEFAULT '09:00',
    state_map   TEXT,
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS jira_sync_log (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id),
    jira_key    TEXT NOT NULL,
    run_id      TEXT REFERENCES agent_runs(id),
    action      TEXT NOT NULL,
    status      TEXT NOT NULL,
    detail      TEXT,
    synced_at   REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_project    ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_state      ON tasks(state);
CREATE INDEX IF NOT EXISTS idx_tasks_sprint     ON tasks(sprint_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent     ON tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_runs_task        ON agent_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_session     ON agent_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_date    ON sessions(date);
CREATE INDEX IF NOT EXISTS idx_sessions_agent   ON sessions(agent_name);
CREATE INDEX IF NOT EXISTS idx_transitions_task ON state_transitions(task_id);
CREATE INDEX IF NOT EXISTS idx_model_usage_run  ON model_usage(agent_run_id);
CREATE INDEX IF NOT EXISTS idx_jira_sync_log_task ON jira_sync_log(task_id);
CREATE INDEX IF NOT EXISTS idx_jira_sync_log_run  ON jira_sync_log(run_id);
"""

MIGRATIONS = [
    "ALTER TABLE projects ADD COLUMN key TEXT",
    "ALTER TABLE tasks ADD COLUMN number INTEGER",
    "ALTER TABLE tasks ADD COLUMN reporter TEXT",
    "ALTER TABLE tasks ADD COLUMN story_points INTEGER",
    "ALTER TABLE tasks ADD COLUMN labels TEXT",
    "ALTER TABLE tasks ADD COLUMN links TEXT",
    "ALTER TABLE state_transitions ADD COLUMN new_assignee TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_number ON tasks(project_id, number)",
    "ALTER TABLE agent_runs ADD COLUMN commit_sha TEXT",
    "ALTER TABLE agent_runs ADD COLUMN commit_message TEXT",
    "ALTER TABLE tasks ADD COLUMN jira_issue_key TEXT",
]

async def apply_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript(DDL)
    await conn.commit()
    # Run migrations safely (ignore "duplicate column" errors)
    for sql in MIGRATIONS:
        try:
            await conn.execute(sql)
            await conn.commit()
        except Exception:
            pass  # column already exists
