#!/usr/bin/env bash
# Run steady-state ingest for ALL configured knowledge-library sources.
# Add a new source: create adopt/config-<name>.yaml, add it to SOURCES below.
set -uo pipefail

SKILL_ROOT="${SKILL_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIBRARY="${LIBRARY:?set LIBRARY to the materialized vault path}"
ADOPT="${ADOPT:?set ADOPT to the directory containing config-*.yaml files}"

SOURCES=(
  "$ADOPT/config.yaml"
  "$ADOPT/config-local.yaml"
  "$ADOPT/config-storm.yaml"
)

for cfg in "${SOURCES[@]}"; do
  echo "=== $(basename "$cfg") ==="
  KNOWLEDGE_LIBRARY_CONFIG="$cfg" \
  LIBRARY="$LIBRARY" \
  SKILL_ROOT="$SKILL_ROOT" \
  bash "$SKILL_ROOT/schedule/wrapper.sh" \
    || echo "WARNING: $(basename "$cfg") failed (exit $?)"
  echo
done
