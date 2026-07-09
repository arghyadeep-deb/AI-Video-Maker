-- Likeness artifacts require a logged consent record (hard invariant,
-- specs/AGENT-PLAYBOOK.md) — voice_profiles had a `consented` flag from
-- 001_init.sql but no timestamp, unlike avatars' own consented_at added in
-- 002_avatar_consent.sql. task-18.
ALTER TABLE voice_profiles ADD COLUMN consented_at TEXT;

-- "M/F prosody base auto-picked from enrollment sample pitch; user-
-- overridable" (specs/04-tasks/task-18-voice-cloning-voxcpm.md) - the
-- edge-tts voice id used as the conversion's prosody base for this
-- profile. Nullable: only ever set for kind='cloned' profiles, not
-- kind='designed' (VoxCPM text-to-voice personas have no base speaker).
ALTER TABLE voice_profiles ADD COLUMN base_voice TEXT;
