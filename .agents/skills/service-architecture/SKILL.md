---
name: service-architecture
description: Apply when changing server-side application logic in src/web.
---

## Services

- Put job orchestration, upload processing, configuration and persistent state in `src/web/`; keep Next.js dependencies out of services when practical.
- Accept dependencies and validated values explicitly where useful. Do not read request context in services.
- Keep model/host allowlists and filesystem boundaries on the server. Use unique per-job input/output directories so separate uploads cannot reuse stale inputs.
- Persist status atomically and make job recovery behavior explicit. Keep logs useful to the user without exposing server paths or secrets.
- Avoid unbounded work: enforce upload limits, one active render, supported formats and worker-count bounds.
