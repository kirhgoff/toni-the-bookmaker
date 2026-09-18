#!/usr/bin/env bash
exec bun "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/src/record/index.ts" "$@"
