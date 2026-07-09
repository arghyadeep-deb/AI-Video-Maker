-- Likeness artifacts require a logged consent record (hard invariant,
-- specs/AGENT-PLAYBOOK.md) — avatars had no consent column, unlike
-- voice_profiles which already had one from 001_init.sql. task-10.
ALTER TABLE avatars ADD COLUMN consented INTEGER NOT NULL DEFAULT 0;
ALTER TABLE avatars ADD COLUMN consented_at TEXT;
