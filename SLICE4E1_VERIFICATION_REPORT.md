# Slice 4E.1 Verification Report - Knowledge Foundation & Canonical Model

## Acceptance results

- `backend/tests/test_4e1_canonical_model.py`: **9/9 passed** (deterministic, no LLM).
- Full backend regression: **655 passed** (646 pre-slice baseline + 9 new slice tests), 0 failures.
- Targeted regression (knowledge services, semantic search, brain evidence/governance/tenant isolation, company brain, phase 20 brain): **59/59 passed**.
- Live-stack acceptance `backend/scripts/accept_slice4e1.py`: **14/14 passed** against `http://localhost:8999`.

## Slice 4E.1 coverage exercised by `accept_slice4e1.py`

1. **Event-driven ingestion contract** - create + publish a document and the existing durable events (`document.created`, `document.published`) land exactly one canonical `KnowledgeSource` (lifecycle `validated`, authority 3 `documented`, freshness `very_high`) with one claim and one primary evidence row.
2. **Registry map** - `GET /brain/knowledge` reports `by_status`/`by_kind` over only what the caller may access; scope `org` for the founder.
3. **Temporal truth** - updating the document supersedes the previous claim (`valid_to` + `superseded_by`) instead of deleting it; the source lifecycle transitions `validated -> updated`; a superseded/current pair is returned together (what was true vs what is true now).
4. **Exact-once event processing** - replaying the same events creates no new claims and does not bump the lifecycle.
5. **Authority model** - an approved policy is `official` (5) with an `authoritative` `effective` claim; published documents are `documented` (3); made decisions are `authoritative` (4).
6. **Decision claims** - choosing an option lands a canonical `decision` claim that names the chosen option as its object.
7. **Topic registry** - the category seeds `knowledge_topics`, the canonical name registry that will seed entity resolution (4E.4).
8. **Bounded reconcile** - `POST /brain/knowledge/reconcile` is hard-capped (`limit <= 100`) and idempotent; normal flow is event-driven, this exists only for recovery.
9. **Tenant isolation** - a rival organization sees `total 0` in the registry, `0` recent claims and `404` on source detail.
10. **Governance** - a project-scoped `brain:read` reader sees only its project's sources in the registry (`scope: project`), gets `404` for hidden sources - governance constrains retrieval itself, nothing is fetched-then-hidden.
11. **Endpoint contract** - anonymous requests are rejected (401/403).
12. **Lifecycle vocabularies** - source lifecycles stay within `discovered|extracted|validated|active|updated|superseded|archived`; claim states within `candidate|supported|authoritative|contested|superseded`.
13. **Freshness model surfaces** - `source_detail` exposes the age-based freshness model (`score`, `label`, `last_verified_at`, `source_updated_at`) and the authority model (`level`, `label`).

## No-LLM determinism guarantee

Slice 4E.1 performs no LLM calls. Canonical ingestion, lifecycle transitions,
claim extraction, authority assignment, freshness scoring and governed reads
are fully deterministic (content hashing, status/kind maps, age thresholds).

## Architecture notes

- **Canonical tables** (`app/models/knowledge.py`): `knowledge_sources`
  (universal ingestion contract; unique per tenant+object, rows never
  deleted), `knowledge_claims` (+ `valid_to`/`superseded_by` temporal chain),
  `knowledge_evidence` (claim -> source link with excerpt), `knowledge_topics`
  (canonical name + alias registry). All tenant-scoped with cascade deletes.
- **Ingestion is event-driven, no new emission sites**: one handler in
  `app/events/handlers.py` subscribes to the existing durable events
  (`*.created|*.updated|*.restored|*.published`, `policy.approved`,
  `decision.made`) and reconciles the canonical row; re-processing unchanged
  content is a no-op.
- **Governed surface** (`app/api/v1/brain.py`, `require_permission("brain:read")`):
  `GET /brain/knowledge`, `GET /brain/knowledge/sources/{type}/{id}`,
  `GET /brain/knowledge/claims`, `GET /brain/knowledge/topics`,
  `POST /brain/knowledge/reconcile` (`brain:manage`). Access is resolved
  governance-first (`resolve_caller_access`) exactly like the existing
  4D semantic retrieval; scoped readers only ever see project-anchored
  sources.
- **Universal contract for 4N**: `kind: internal` and `external_ref` columns
  are already present, so 4E.2/4N adapters (Drive, Slack, Jira, ...) will
  land in the same registry and be consumed identically.
- **Bound design**: registry reads cap candidates (`60`), claims (`100`),
  topics (`50`); reconcile is hard-capped. No full-org scans anywhere.
  Remaining 4E.1-adjacent work (real claim extraction, graph joins, UI) is
  deliberately deferred to 4E.2-4E.11 per the sub-slice plan.

## Repository state

- Committed as `vcos-slice-4e1-complete` (see tag `vcos-slice-4e1-complete`).
- Working tree clean.
- Slice 4E.1 is the first controlled increment of 4E; next increment per the
  plan: **4E.2 - Universal Knowledge Ingestion** (messages, chats, tasks,
  meetings, memory/pattern feeds + external contract).