#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$ROOT/.runtime/rea-tools/node_modules"
if [[ ! -x "$RUNTIME/node/bin/node" || ! -f "$RUNTIME/rea-agents/scripts/rea.mjs" ]]; then
  echo 'REA runtime missing. See docs/REA_CHATGPT_REFERENCE.md.' >&2
  exit 1
fi
exec "$RUNTIME/node/bin/node" "$RUNTIME/rea-agents/scripts/rea.mjs" "$@"
