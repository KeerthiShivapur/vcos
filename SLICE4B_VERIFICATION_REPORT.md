# VCOS Slice 4B — Verification Report

Status: **COMPLETE** — tag `vcos-slice-4b-complete` (re-created on the
universal-scale rework commit; supersedes the earlier `0fba434` tag).

## Universal-scale constraint (mandate)

VCOS must run on one canonical architecture from a 1-person company to a
50,000+ employee enterprise — org size must **never** select a different code
path, and no operation may do O(N) work where N = org employees or
conversation members unless it is explicitly targeted and bounded.

### Notification design (reworked)

- **Ordinary channel messages are NOT per-member notification rows.** A sent
  message persists once, emits `messaging.message_sent`, and is delivered to
  subscribed members via realtime (event bus → LiveHub personal channels);
  the 30s polling fallback covers offline/unsubscribed readers. Unread state
  remains computed (read receipts), not row-per-member.
- **Notification rows are created only for targeted, bounded signals**:
  - DM recipient (2-person conversation — bounded by construction; adding a
    third member to a DM is now refused, 400)
  - Reply author (O(1) lookup via `reply_to`)
  - @mentions (mentioned employees only, via `notify_mentions`)
  - Membership changes (`messaging.member_added` / `messaging.member_removed`
    events already emitted by add/remove member)
- Reuses the existing event bus, LiveHub, NotificationService, AuditService,
  SearchService, tenancy, and permission system — no second messaging/
  queue/realtime architecture, no new worker processes, no per-connection DB
  sessions.

### Implementation delta

`backend/app/communication/message_service.py` — `send()` no longer loops
conversation members for ordinary messages; it notifies the DM recipient
(`type == "dm"`) and the reply author only, then `notify_mentions`.
`add_member()` refuses DMs (`ValueError` → 400 via router).
`backend/tests/test_messaging.py` — three new tests pin the contract:
no per-member notification for an ordinary channel message, reply notifies
the original author only, and DM third-member add is refused (15 tests total).

## Acceptance gate results

| Gate | Result |
|---|---|
| Backend pytest suite | **519 passed, 0 failed** (24:22) |
| Playwright E2E suite (slice1–7 + slice4a + slice4b, 11 tests) | **11/11 passed** (final run 4.8m; slice4b spec standalone 2.7–3.4m) |
| `scripts/accept_slice1.py` (live API) | **34 passed, 0 failed** |
| `scripts/accept_slice2.py` (live API) | **32 passed, 0 failed** |
| `scripts/accept_slice3.py` (live API) | **35 passed, 0 failed** |
| `scripts/accept_slice4a.py` (live API) | **32 passed, 0 failed** |
| `scripts/accept_slice4b.py` (live API) | **28 passed, 0 failed** (incl. queue-drain, mention + DM notifications, event/audit verification) |
| `npx next build` / `npx tsc --noEmit` | **clean** |
| Working tree | **clean** (single commit, tag `vcos-slice-4b-complete`) |

All acceptance scripts run against the live backend (`:8999`) with fresh
tenants, invite/accept flows, tenant-isolation checks, live event-worker
notification delivery, and the synchronous realtime fallback path.

## Delivered scope

- **Messaging core (4B.1)**: 11 endpoints — DM open/find-or-create, conversation
  create/update/archive/members, message send/update/soft-delete, reactions
  (toggle), read receipts (message + conversation), pinned messages. `communication:read`
  / `communication:write` RBAC (employee role is read-only: 403 on mutations,
  200 on lists).
- **Operating loop (4B.2)**: every action flows through the Event Bus —
  `messaging.conversation_created`, `messaging.message_sent`,
  `messaging.message_updated`, `messaging.message_deleted`,
  `messaging.message_reaction_added`, `messaging.message_reaction_removed`,
  `messaging.member_added`, `messaging.member_removed` — with audit rows and
  targeted notifications only (DM recipient, reply author, @mentions via the
  event worker; scale-neutral, see above).
- **Realtime (4B.3)**: `GET /ws/messaging` personal channel on the shared
  LiveHub (`/ws/meetings` pattern) — welcome frame, per-employee fan-out,
  zero DB work per frame; cross-process delivery via the 30s polling fallback
  (no new worker processes, Redis disabled). Realtime — not notification
  rows — is the delivery path for ordinary channel messages.
- **Universal search (4B.4)**: member-scoped `conversation` + `message` hits
  in `SearchService` (`type: conversation|message`, deleted messages and
  non-member conversations excluded, content/title/channel_key LIKE matches).
- **Frontend realtime (4B.5)**: `messagingChannel` WS singleton
  (token query, 25s heartbeat, capped exponential backoff, teardown on zero
  listeners); live messages page — optimistic send, inline edit, delete with
  confirm + tombstone, reaction toggle, `(edited)` marker, read-receipt
  marking, 30s fallback poll with fresh-row diff.
- **Tests**: `backend/tests/test_messaging.py` (15 tests incl. universal
  search + WS frames + events + audit + scale-neutral notification contract),
  `frontend/e2e/slice4b-messaging.spec.ts`
  (full two-browser lifecycle: invite → DM → send → edit → react → delete →
  search → event trail).

## Bug fixes surfaced by verification

- **Read-receipt race (500s in production, found via E2E)**: `mark_read` and
  `mark_conversation_read` did check-then-insert; the frontend fires
  `markConversationRead` and per-message `markMessageRead` concurrently, so
  two inserts raced and one blew up on `uq_message_read_receipts_reader`.
  Both now use atomic `INSERT … ON CONFLICT DO NOTHING`.
- **Mutation retry duplicated messages**: `fetchWithRetry` retried POST/PATCH/
  DELETE on network errors. Under load a message POST timed out client-side
  (2.5s cap) but still reached the server — the retry created a duplicate
  (proven from browser trace: two POSTs, `time: -1` then 201). Only idempotent
  GETs are auto-retried now; the 401 token-refresh re-issue (safe: rejected
  request) is preserved for all methods.
- **`document.hidden` poll freeze**: the 30s fallback poll skipped when the
  tab reported hidden — in Playwright headless, backgrounded contexts report
  `document.hidden === true`, so Bob's parked tab stopped receiving updates
  mid-test (and real users in background tabs would stall too). Guard removed.
- **DM creation emitted no event**: `find_or_create_dm` created the
  conversation without `messaging.conversation_created` (channels emitted it;
  DMs didn't). Now emitted on the create path with `ip_address`.
- **Stale frontend type**: `FollowUpAction` was missing `owner_name`, breaking
  `next build` (pre-existing from 4A; backend already returned the field).
- **Universal search 500 on twin recommendations** (rework run): the search
  `recommendation` section indexed `r['priority']`, but
  `ExecutiveRecommendation` has no `priority` field (it uses `impact`) — any
  org with an active twin recommendation got a 500 on `GET /search`. Now
  falls back to `impact`/`medium`.
- **2.5s client request cap aborted slow cold-starts**: the per-attempt
  timeout aborted first-time requests (e.g. org registration on a cold API
  worker) that would have succeeded; the client showed "signal is aborted"
  and the test stayed on the register form. Cap raised to 10s (normal
  requests still complete in well under a second).

## Regression notes

- **Cross-process realtime reality**: Redis is disabled and the event worker
  is a separate process, so the WS personal-channel fan-out is verified via
  backend tests (`LiveHub` frames); browser delivery in the live stack is the
  30s polling fallback (directly observed: 30.1s / 30.2s poll cycles in the
  E2E). Specs allow 60s windows.
- **Playwright selectors**: DM starter buttons expose Avatar initials in their
  accessible name (`DB Dia Bob…`), so role selectors must use substring regex,
  never `^…$` anchors.
- **`next build` must not run while `npm run dev` is up** — both write
  `.next`; the build overwrote the dev server's chunks and broke served
  routes (one E2E failure was this corruption, resolved by restarting dev).
- **Search excludes soft-deleted messages** by design; the acceptance script
  originally searched for a message it had just deleted — fixed in the script
  (a live message is searched instead).
- **Flaky-spec fixes during the rework battery**: strict-mode violation on
  `heading "Organization"` (substring match — now `exact: true`); sprint
  planning double-clicked one Add button because the interim assertion was
  vacuous (waits on the Add-button count now); invite-URL wait widened to 30s
  (the invite UI's drop-recovery dance can exceed 10s); project page-load
  waits widened to 30s (a dropped page-load fetch is retried once at up to
  10s per attempt).
- The diagnostic spec used during debugging (`e2e/diag-messaging.spec.ts`)
  was deleted after the main spec went green.

Out of scope (untouched, per plan): RBAC refinement (4C), intelligence/
autonomy (4D), twin/autonomy decision duplicates.
