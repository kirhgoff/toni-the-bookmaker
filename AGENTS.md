# Project guidance

Toni is a Bun/TypeScript audiobook driver with a Next.js App Router web interface and a Python TTS pipeline. The web application delegates rendering to the existing driver; do not duplicate the render pipeline in route handlers.

## Boundaries and conventions

- Before editing, read the matching skill in `.claude/skills/`: `controllers` for `app/`, `service-architecture` for `src/web/`, `module-boundaries` for imports/new files, `error-handling` for failures, and `better-ui` for presentation work.
- Keep route handlers small: authorize, validate request boundaries, invoke a service, and map results to HTTP responses.
- Keep uploads, job state, audio and host credentials out of git. Configure storage and runtime behavior through environment variables; `hosts.local.json` is local-only.
- Never expose server filesystem paths or secrets through API responses. Constrain uploaded file types/sizes, validate all render options, and confine downloads to completed jobs.
- Do not commit environment files. `.env.example` is the documented template.

## Verify

Run `bun test`, `bun run typecheck`, and `bun run build` after changes. For changes to remote rendering, also verify against a configured test host rather than embedding machine-specific settings in source or docs.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
