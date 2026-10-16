---
name: error-handling
description: Apply when handling failures in upload, job, process, or route code.
---

## Error handling

- Validate expected user mistakes explicitly and return actionable 4xx messages without exposing local paths.
- Capture subprocess exit status and stderr in the protected job log; persist a clear failed state and user-safe summary.
- Do not silently swallow unexpected errors. If recovering from missing/corrupt persisted data, keep the fallback narrow and report safe diagnostics server-side.
- Make downloaded output available only after success and verify it exists beneath the configured library root.
