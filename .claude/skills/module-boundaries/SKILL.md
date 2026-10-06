---
name: module-boundaries
description: Apply when adding files or imports to Toni's web and render code.
---

## Module boundaries

- `app/` contains pages and thin HTTP controllers; `src/web/` owns web services and job state; `src/record/` remains the audiobook driver; `src/toni/` remains the Python TTS pipeline.
- Do not import route/page modules into services or have controllers bypass the service layer for filesystem or process work.
- Keep API response types separate from persisted job records; never serialize private fields by spreading internal objects.
- Keep configuration examples generic and secrets, local hosts, generated output and uploaded content out of tracked files.
