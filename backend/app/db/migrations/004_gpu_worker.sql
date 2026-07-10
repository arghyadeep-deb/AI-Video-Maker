-- Home GPU worker (task-20a) — specs/03-design/11-gpu-worker.md.
-- gpu_tasks is a *separate* queue from jobs: a jobs row is a user-visible
-- pipeline run on the VM; a gpu_tasks row is one GPU sub-step of such a run
-- (a SadTalker render, one scene's generated-footage clip) handed to the
-- owner's PC over the pull-worker protocol while the pipeline awaits it.

CREATE TABLE IF NOT EXISTS gpu_tasks (
    id                TEXT PRIMARY KEY,
    kind              TEXT NOT NULL,              -- 'sadtalker' | 'voxcpm' | 'musetalk' | 'scene_gen'
    status            TEXT NOT NULL DEFAULT 'queued',  -- queued | leased | done | failed | cancelled
    payload_json      TEXT,                       -- engine parameters (prompt, duration, format…)
    input_files_json  TEXT,                       -- [{"name": …, "path": …}] on the VM, served via signed URLs
    result_path       TEXT,                       -- where the uploaded result landed on the VM
    error             TEXT,
    progress          REAL NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0, -- lease grants so far; expiry past max => failed
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    leased_at         TEXT,
    last_heartbeat_at TEXT,
    finished_at       TEXT
);

-- Single-row presence record: every worker poll stamps it. "Online" is
-- computed as last_poll_at within a freshness window, never stored — a
-- sleeping PC simply stops polling (normal event, not an error).
CREATE TABLE IF NOT EXISTS worker_status (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    last_poll_at      TEXT NOT NULL,
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    vram_free_mb      INTEGER
);

-- One-time signed download tokens for gpu_task input files. The URL is the
-- credential (engine subprocesses on the agent fetch without headers);
-- nothing else on the VM is reachable with it.
CREATE TABLE IF NOT EXISTS signed_urls (
    token       TEXT PRIMARY KEY,
    gpu_task_id TEXT NOT NULL REFERENCES gpu_tasks(id),
    path        TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_gpu_tasks_status ON gpu_tasks(status);
CREATE INDEX IF NOT EXISTS idx_signed_urls_task ON signed_urls(gpu_task_id);
