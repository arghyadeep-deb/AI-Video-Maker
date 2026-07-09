# High-Level Architecture

```mermaid
flowchart TB
    subgraph Vercel["Vercel (free) — Next.js Frontend"]
        Auth["Register / Login"]
        Create["Create page"]
        Editor["Script Editor"]
        ModeUI["Mode Select + Avatar/Voice setup"]
        Progress["Queue + Progress"]
        Library["Library + Player + Post-render tools"]
    end

    subgraph VM["Oracle Always Free VM (2 OCPU/12GB) — Caddy HTTPS"]
        subgraph API["FastAPI"]
            AuthAPI["/api/auth/* (fastapi-users, JWT)"]
            Quota["credit + quota middleware"]
            Routes["/api/projects · script · avatars · voices · video · jobs"]
        end
        subgraph Worker["Async Job Worker (fair round-robin)"]
            BPipe["Mode B pipeline"]
            APipe["Mode A pipeline"]
            Post["swap-image / scene & mode re-render"]
        end
        Engines["Engine Interfaces:<br/>ScriptLLM · ImageStyler · TTSEngine ·<br/>TalkingHeadEngine · StockImages · FFmpeg"]
        DB[("SQLite (users, projects, jobs, credits)")]
        FS[("media/ per-user")]
    end

    subgraph External["Free external services (owner's key pool)"]
        Gem["Gemini Flash + Flash Image"]
        Edge["edge-tts"]
        Stock["Pexels / Pixabay"]
        Zero["HF ZeroGPU Space:<br/>SadTalker · VoxCPM · MuseTalk"]
    end

    Vercel -->|HTTPS JSON| API
    API --> Worker
    Worker --> Engines
    Engines --> Gem & Edge & Stock & Zero
    API --> DB
    Worker --> DB & FS
```

## Layers

- **Frontend (Vercel)**: seven views ([`10-frontend-pages.md`](./10-frontend-pages.md)) incl. auth pages. Talks JSON to the VM; polls job status.
- **FastAPI on the VM**: auth (`fastapi-users`, JWT cookies), then a **credit/quota middleware** every mutating route passes through, then thin CRUD/job routes. Script generate/improve are synchronous; all media work is a job.
- **Job worker**: single-process async worker with **per-user round-robin fairness** and queue-position reporting ([`07-job-queue-and-progress.md`](./07-job-queue-and-progress.md)). CPU jobs run on the VM; GPU stages call the ZeroGPU Space via `gradio_client` under a daily GPU-seconds budget.
- **Engine interfaces**: every external/free dependency sits behind a small typed interface so fallbacks swap without pipeline changes.
- **Storage**: SQLite (users, projects, versions, jobs, credits, usage) + per-user media folders; retention policy prunes old renders ([`02-research/08-free-hosting.md`](../02-research/08-free-hosting.md)).

Source diagram: [`05-flowcharts/01-high-level-architecture.mmd`](../05-flowcharts/01-high-level-architecture.mmd).
