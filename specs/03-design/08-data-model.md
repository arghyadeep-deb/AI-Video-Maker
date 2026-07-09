# Data Model (SQLite)

```mermaid
erDiagram
    users ||--o{ projects : owns
    users ||--o{ avatars : owns
    users ||--o{ voice_profiles : owns
    users ||--o{ credits : "daily"
    projects ||--o{ script_versions : has
    projects ||--o{ jobs : has
    projects ||--o{ media_assets : has
    projects }o--o| avatars : uses
    avatars ||--o{ media_assets : "selfie/portrait"

    users {
        text id PK
        text email UK
        text password_hash "argon2"
        int verified "0|1"
        text role "user|admin"
        datetime created_at
    }
    credits {
        text user_id FK
        date day
        int videos_used
        int scripts_used
        int stylings_used
        int gpu_slots_used
    }
    voice_profiles {
        text id PK
        text user_id FK
        text kind "enrolled|designed"
        text description "for designed voices"
        text sample_path "enrollment recording"
        text embedding_path "OpenVoice tone-color embedding"
        int consented "0|1"
        datetime created_at
    }
    projects {
        text id PK
        text user_id FK
        text title
        text description
        text language "hi|en"
        int duration_s "30|60|120|300"
        text format "9x16|16x9"
        text status "drafting|script_ready|accepted|generating|done|failed"
        text mode "a|b|null"
        text voice "edge-tts voice id"
        text accepted_version_id FK
        text output_path
        datetime created_at
    }
    script_versions {
        text id PK
        text project_id FK
        int n
        text scenes_json
        text origin "generated|improved|edited"
        datetime created_at
    }
    avatars {
        text id PK
        text user_id FK
        text name
        text persona_description
        text selfie_path
        text portrait_path
        int approved "0|1"
        datetime created_at
    }
    jobs { text id PK }
    media_assets {
        text id PK
        text project_id FK
        text kind "audio|image|subtitle|raw_video|output"
        int scene_id "nullable"
        text path
        text meta_json "credits, engine, timings ref"
    }
```

(`jobs` columns detailed in [`07-job-queue-and-progress.md`](./07-job-queue-and-progress.md).)

## Notes

- **Every user-owned table carries `user_id`; every query filters on it.** Account deletion cascades rows + media folders (`media/users/<uid>/…`).
- `credits` rows are upserted per `(user_id, day)` and decremented atomically with job creation; limits themselves live in config, not the DB ([`01-requirements/10-hosting-accounts-quotas.md`](../01-requirements/10-hosting-accounts-quotas.md)).
- `voice_profiles.consented` gates cloned voices the same way avatar consent gates selfies.
- `scenes_json` = the validated script contract array (`[{id, text, visual_hint, visual_hint_stale}]`). Scenes are a JSON column, not a table — they're always read/written as a unit with their version.
- `avatars` is project-independent by design: approve once, reuse forever (requirement in [`04-mode-a-avatar.md`](../01-requirements/04-mode-a-avatar.md)).
- Filesystem layout mirrors the DB: `media/users/<uid>/projects/<id>/{audio/,images/,subs/,output.mp4,credits.txt}` and `media/users/<uid>/avatars/<id>/{selfie,portrait}.png`. DB stores paths; files are the payload. Deleting a project deletes its folder; a retention job prunes rendered MP4s after N days (config; scripts/projects stay re-renderable).
- IDs: UUIDv7 strings (sortable).
- Migrations: plain numbered SQL files applied at startup (no Alembic ceremony for SQLite).
- Word-timing arrays are stored as JSON files next to the audio they describe (`audio/scene-3.timings.json`), referenced from `media_assets.meta_json` — too bulky and too single-purpose for DB rows.
