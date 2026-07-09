-- Initial schema — specs/03-design/08-data-model.md, specs/03-design/07-job-queue-and-progress.md
-- IDs are UUIDv7 strings (sortable), generated in application code.

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    verified      INTEGER NOT NULL DEFAULT 0,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Per-user daily allowances. specs/01-requirements/10-hosting-accounts-quotas.md
-- (locked decision) drops per-user credit *rationing* in favor of global-only
-- guards for a 1-2 user site, but specs/03-design/08-data-model.md and
-- specs/03-design/07-job-queue-and-progress.md still model this table for
-- per-user usage visibility ("2 of 3 videos left today" style UI, if ever
-- reintroduced). Kept per the data model; task-15 (quotas-fairness) decides
-- whether it's actually enforced or purely informational — see
-- specs/04-tasks/PROGRESS.md for this flagged discrepancy.
CREATE TABLE IF NOT EXISTS credits (
    user_id        TEXT NOT NULL REFERENCES users(id),
    day            TEXT NOT NULL,
    videos_used    INTEGER NOT NULL DEFAULT 0,
    scripts_used   INTEGER NOT NULL DEFAULT 0,
    stylings_used  INTEGER NOT NULL DEFAULT 0,
    gpu_slots_used INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

-- Global per-provider counters, enforced by the quota middleware (task-15).
CREATE TABLE IF NOT EXISTS usage (
    date    TEXT NOT NULL,
    counter TEXT NOT NULL,
    n       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, counter)
);

CREATE TABLE IF NOT EXISTS voice_profiles (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id),
    kind           TEXT NOT NULL,
    description    TEXT,
    sample_path    TEXT,
    embedding_path TEXT,
    consented      INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS avatars (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL REFERENCES users(id),
    name                TEXT,
    persona_description TEXT,
    selfie_path         TEXT,
    portrait_path       TEXT,
    approved            INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- accepted_version_id forward-references script_versions, created below;
-- SQLite does not require the referenced table to exist yet at DDL time.
CREATE TABLE IF NOT EXISTS projects (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL REFERENCES users(id),
    title               TEXT,
    description         TEXT,
    language            TEXT NOT NULL,
    duration_s          INTEGER NOT NULL,
    format              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'drafting',
    mode                TEXT,
    voice               TEXT,
    accepted_version_id TEXT REFERENCES script_versions(id),
    output_path         TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS script_versions (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    n           INTEGER NOT NULL,
    scenes_json TEXT NOT NULL,
    origin      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id),
    project_id   TEXT REFERENCES projects(id),
    type         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued',
    stage        TEXT,
    progress     REAL NOT NULL DEFAULT 0,
    payload_json TEXT,
    result_json  TEXT,
    error        TEXT,
    engine_notes TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    started_at   TEXT,
    finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS media_assets (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    kind       TEXT NOT NULL,
    scene_id   INTEGER,
    path       TEXT NOT NULL,
    meta_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_credits_user      ON credits(user_id);
CREATE INDEX IF NOT EXISTS idx_voice_profiles_u  ON voice_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_avatars_user      ON avatars(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_user     ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_script_versions_p ON script_versions(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user         ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status       ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_media_assets_proj ON media_assets(project_id);
