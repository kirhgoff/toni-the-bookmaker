---
name: controllers
description: Apply when editing Next.js pages or route handlers. Keep controllers thin and validate untrusted requests.
---

## Controllers

- `app/` is the web/controller layer. Route handlers authorize, parse request data, call a service from `src/web/`, and map success/failure to HTTP responses.
- Keep file handling and render/job rules in services, not handlers or React components.
- Treat form data, filenames, URLs and IDs as untrusted. Validate sizes, types, supported models and configured hosts at the server boundary.
- Return only the fields the browser needs. Never return filesystem paths, credentials, stack traces or raw internal exception messages.
- Protect mutations and downloads with the configured web token. Use clear status codes and actionable but non-sensitive errors.
