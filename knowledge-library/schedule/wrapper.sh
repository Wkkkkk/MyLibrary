#!/usr/bin/env bash
# knowledge-library steady-state trigger (spec §7/§10).
#
# This is BOTH the manual one-command trigger and the launchd target. It runs
# locally (where the source cookie lives), spends LLM ONLY when there are
# net-new articles, and records every run in the ledger so a silent fetch
# failure is visible (see references/lessons.md — cookie-expiry caveat).
#
# Fill in the three CONFIG values below, then:  bash schedule/wrapper.sh
# Run by hand until trusted; then enable schedule/com.user.knowledge-library.plist.
set -euo pipefail

# ---- CONFIG (fill in) ----------------------------------------------------
SKILL_ROOT="${SKILL_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"   # the knowledge-library/ dir
export KNOWLEDGE_LIBRARY_CONFIG="${KNOWLEDGE_LIBRARY_CONFIG:-$SKILL_ROOT/config.yaml}"
LIBRARY="${LIBRARY:?set LIBRARY to your materialized vault path (config library_path)}"
FETCH_CMD="${FETCH_CMD:-}"   # e.g. "python ~/workspace/playground/zhihu/fetch.py" — empty = skip fetch
# --------------------------------------------------------------------------

cd "$SKILL_ROOT"
LOG_DIR="$SKILL_ROOT/logs"; mkdir -p "$LOG_DIR"
DIGEST="$LOG_DIR/$(date +%F).md"

# 1. Fetch new source articles into the inbox (breakpoint-resume; only pulls new).
if [ -n "$FETCH_CMD" ]; then
  echo "fetch: $FETCH_CMD"
  $FETCH_CMD || echo "WARNING: fetch failed (cookie expired? check \`librarian status\`)"
fi

# 2. Net-new by url — pure Python, no LLM. cmd_diff (library mode) prints "N new inbox article(s)".
NEW="$(python -m librarian.update diff --out "$LIBRARY" | grep -oE '^[0-9]+' | head -1 || echo 0)"
NEW="${NEW:-0}"
echo "diff: $NEW net-new article(s)"

# 3. Label + finish ONLY if there is new work — headless LLM, bounded to net-new.
if [ "$NEW" -gt 0 ]; then
  claude -p "Run the knowledge-library skill in steady-state for $NEW net-new inbox \
article(s): build one labeling wave, dispatch the labeling agents, then run \
librarian.orchestrate.steady_state.finish to ingest -> materialize into '$LIBRARY' \
-> verify and append a run-ledger row. Use config.label_model. Do not pause at gates \
(steady-state is non-blocking: record proposed_topics + needs_review and continue)."
else
  # Nothing new: record a zero-cost empty pull so the ledger/status stay current.
  python - <<'PY'
import os, datetime
from librarian import config
from librarian.orchestrate import steady_state
cfg = config.load(os.environ["KNOWLEDGE_LIBRARY_CONFIG"])
now = datetime.datetime.now().isoformat(timespec="seconds")
steady_state.record_nothing_new(cfg, run_id=f"run-{now}", started_at=now, finished_at=now)
PY
fi

# 4. Digest from the run ledger (the latest row + pending queues).
python -m librarian.update status | tee "$DIGEST"
echo "digest -> $DIGEST"
