# The three gates — playbook, heuristics, pause protocol

Bootstrap labeling is autonomous *between* gates and **pauses** at each gate for human sign-off. The gates are where taxonomy judgment lives; the toolkit can't make these calls.

## Pause protocol (every gate)

1. **Stop the loop.** Do not proceed past a gate without explicit sign-off.
2. **Render the decision.** Present a compact summary (the numbers + the specific proposed changes), not raw dumps.
3. **Get an explicit decision.** Accept / revise / reject — in the user's words.
4. **Apply once, then continue.** Make the agreed change, then resume. Don't re-open a closed gate later in the same run.

## 🚦 GATE 1 — 25% taxonomy audit

**When:** after ~25% of the corpus is labeled (enough signal, cheap to revise).
**Goal:** revise the canon **once** — split overgrown topics, merge thin ones — before it ossifies.
**Inputs:** `python -m librarian.update audit` — prints `category_sizes`, `split_candidates`, `merge_candidates`, `proposals`, and the open review count. `python -m librarian.update status` also shows the pending proposal + review counts.
**Heuristics:**
- A topic with **> `topic_split_threshold`** (default 40) articles is a **split candidate** — too coarse to browse.
- A topic with **< `hub_min_articles`** (default 3) articles is a **merge candidate** — too thin to earn a hub.
- A `primary_category` that's swallowing everything is a sign the canon is too coarse; one that's near-empty, too fine.
**Action:** agree the split/merge set, edit `data_dir/topics.tsv` (and re-label affected rows if a category boundary moved), sign off, finish the waves.

## 🚦 GATE 2 — proposals triage

**When:** after 100% labeled.
**Goal:** promote the good agent-proposed topics into the active canon so the library closes green.
**Inputs:** `python -m librarian.update proposals` — lists each pending proposal with its article count + an example.
**Decision per proposal:** **accept** (promote to active), **reject** (the articles fall back to their best-fit active topics), or **merge** (alias it onto an existing active topic via the registry).
**Action:** `python -m librarian.update proposals --accept` promotes all pending; for selective accept/merge, edit `topics.tsv` directly (set `status: active`, or add the proposal as an `aliases` entry on the target). Sign off, then re-run materialize + verify.

## 🚦 GATE 3 — review queue

**When:** after proposals triage.
**Goal:** drive `needs_review` rows to **zero** so nothing ambiguous ships unresolved.
**Inputs:** the audit report's `review_open` count; the rows with `needs_review == true` + their `review_reason`.
**Action:** resolve each (fix the label, accept the best-fit, or re-label), clear the flag, sign off.

## Steady-state: the deferred gate

In steady-state runs the gates do **not** block — a new article that doesn't fit is labeled best-fit with `proposed_topics` + `needs_review` set, and the run continues (non-blocking, spec §7). Proposals/review accumulate into the queue you drain interactively on your own cadence — run GATE 2 + GATE 3 by hand whenever `python -m librarian.update status` shows pending items worth a pass.
