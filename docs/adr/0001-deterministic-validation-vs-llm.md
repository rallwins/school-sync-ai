# ADR 0001: Deterministic validation, not an LLM, decides dates, identity and sync

Status: accepted. The shipped extractor uses no LLM at all.

**Context.** Calendar PDFs need date arithmetic, half-day/all-day decisions, duplicate decisions
and write operations. LLM output is non-deterministic and can invent plausible dates or times.

**Decision.** Everything authoritative is plain code: grid-to-date mapping (cross-checked against the
printed day number), colour-to-legend matching (CIE76 ΔE with a tolerance), keyword/time rules,
fingerprints, duplicate layers, planning and execution. An LLM, if added, may only help read
free-text titles or legend wording; its output must be schema-validated and checked against the
page evidence, and it can never set a date, an identity, a duplicate verdict or trigger a write.

**Consequences.** Behaviour is reproducible and unit-testable (see `test_extraction.py`,
`test_fixture_b.py`). Coverage is narrower: the keyword rules will miss phrasings they do not
know, which then surface as `needs_review`, not as silent guesses. A local-model assist is a
roadmap item, not implemented.
