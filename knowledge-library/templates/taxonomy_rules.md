# Taxonomy rules

> Copy this to `rules/taxonomy_rules.md` and fill it in. Each labeling agent reads
> this file alongside the active topic canon. It is the single source of truth for
> how to classify — keep it tight and example-driven. No canon yet? Label a ~20-30
> article pilot first, then write these rules from what you saw.

## Output contract (do not deviate)

Emit one JSON object per article with exactly these fields:

- `relative_path` — copy verbatim from the assignment (the row key).
- `primary_category` — **exactly one**, from the canon list below. Never invent one.
- `topics` — 1-5 reusable subjects. Reuse a canon topic when it fits; only when nothing fits, add a new one AND repeat it in `proposed_topics`.
- `tags` — free keywords: people, works, products, events. No vocabulary.
- `article_type` — one of the controlled forms below.
- `summary` — ONE sentence, **in the article's own language** (do not translate).
- `confidence` — `high` / `medium` / `low`.
- `needs_review` — `true` only when you are genuinely unsure.
- `review_reason` — one-line explanation; required (non-empty) when `needs_review` is `true`, else empty.
- `proposed_topics` — any topic in `topics` that is NOT already in the active canon.

**Language:** classify into the canon language named in the assignment header (English). Propose new topics in that language. The summary stays in the article's own language.

## The three recurring slips (the validator rejects these)

1. **A category name used as a topic** (e.g. topic `"AI & Machine Learning"`). Categories and topics are different axes — never cross them.
2. **An `article_type` used as a topic** (e.g. topic `"tutorial"`). article_type is its own field.
3. **Path-unsafe topic names** — no `/`, `\`, or `:` in a topic name.

## primary_category canon

<!-- Paste your locked English category list here, each with a one-line boundary. -->
- `<Category>` — <when an article belongs here vs the neighbouring category>
- …

## article_type vocabulary

<!-- The controlled forms-of-writing for YOUR corpus. Starter set: -->
- `tutorial` — step-by-step how-to
- `Q&A` — question-and-answer / problem-solution
- `academic` — paper-style explanation or literature review
- `resource-list` — curated links/recommendations
- `review` — opinion/evaluation of a work, product, or idea
- `experience-share` — first-person account / case study
- `news` — event report or announcement

## Topic conventions

- Prefer an existing canon topic over a near-synonym (the registry resolves aliases, but consistency helps).
- A topic should be reusable across many articles — if it would apply to only this one article, it's a `tag`, not a `topic`.
- Topics that grow past ~40 articles get split at GATE 1; topics under 3 get merged. Don't over-fragment up front.
