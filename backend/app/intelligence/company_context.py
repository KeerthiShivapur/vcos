"""Slice 4D.1 — canonical company intelligence & evidence layer.

The one governance-scoped context builder for the Company Brain. Every
consumer (reasoning engine, search, event handlers, workers) retrieves
company facts through this module so the whole estate obeys the same rule:

    caller -> user -> organization -> roles -> governance scopes
              -> accessible IDs -> retrieve only accessible information
              -> bounded evidence context -> reason

Authorization model (matches 4C governance semantics, downward-only):

* A caller holding any organization-wide role assignment (UserRole.scope_id
  is NULL) sees the entire organization — the flat-role behavior every
  pre-4D feature already relies on.
* A caller with only scope-anchored assignments sees exactly their visible
  scope subtree: the anchored scope, its descendants, scope-anchored
  approval policies, and entities the scopes wrap through
  GovernanceScope.entity_id (project-type scopes). Conversation/message
  evidence is additionally gated on membership.
* Evidence is never fabricated: every item references a real row via its
  primary key, and every item carries the id needed to link back.

Boundary laws enforced here:

* No O(N) scans: every candidate fetch is an indexed organization-scoped
  query with a hard limit; entity resolution is deterministic token
  matching (no ``LIKE '%q%'``) over bounded candidate batches.
* No unbounded traversal: scope ancestry and descendants are walked with
  hard depth/node caps (MAX_SCOPE_DEPTH mirrors governance_service).
* Bounded output: evidence, relations and entity mentions are capped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import Conversation, ConversationMember, Message
from app.models.employee import Employee
from app.models.finance import Budget
from app.models.goal import Goal
from app.models.governance import ApprovalPolicy, GovernanceScope
from app.models.knowledge import Decision
from app.models.project import Project
from app.models.task import Task
from app.services.governance_service import governance_service

MAX_SCOPE_DEPTH = 32
MAX_SCOPE_NODES = 512
MAX_CANDIDATES_PER_TYPE = 50
MAX_RESOLVE_IDS = 200
DEFAULT_CONTEXT_LIMIT = 24
FALLBACK_RECENT_PER_TYPE = 5

EVIDENCE_TYPES = (
    "project",
    "task",
    "decision",
    "conversation",
    "message",
    "scope",
    "approval_policy",
    "goal",
    "budget",
    "employee",
    "document",
    "wiki",
    "policy",
    "sop",
    "template",
)

# Slice 4D.2 — knowledge kinds the brain can cite as evidence. Access mirrors
# the retrieval law: org-wide callers see published knowledge; scoped callers
# only see project-anchored documents/wikis whose project is inside their
# visible scope subtree (policies/SOPs/templates have no project anchor and
# are org-wide only — conservative downward-only behavior).
KNOWLEDGE_EVIDENCE_KINDS = ("document", "wiki", "policy", "sop", "template")
KNOWLEDGE_PUBLISHED = ("published", "approved", "made", "implemented", "reviewed")

# Evidence type -> (model, frontend url template, matchable text fields,
#                   source label). Deterministic keyword classifier below.
_EVIDENCE_META: dict[str, dict[str, Any]] = {
    "project": {"source": "projects", "url": "/projects/{}"},
    "task": {"source": "tasks", "url": "/tasks/{}"},
    "decision": {"source": "decisions", "url": "/decisions/{}"},
    "conversation": {"source": "conversations", "url": "/messaging/{}"},
    "message": {"source": "messages", "url": "/messaging/messages/{}"},
    "scope": {"source": "governance_scopes", "url": "/governance/scopes/{}"},
    "approval_policy": {"source": "approval_policies", "url": "/governance/approval-policies/{}"},
    "goal": {"source": "goals", "url": "/goals/{}"},
    "budget": {"source": "budgets", "url": "/finance/budgets/{}"},
    "employee": {"source": "employees", "url": "/people/{}"},
    # Slice 4D.2 — knowledge evidence (urls follow the knowledge entity routes)
    "document": {"source": "documents", "url": "/documents/{}"},
    "wiki": {"source": "wiki_pages", "url": "/wiki/{}"},
    "policy": {"source": "policies", "url": "/policies/{}"},
    "sop": {"source": "sops", "url": "/sops/{}"},
    "template": {"source": "templates", "url": "/templates/{}"},
}

_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "project": ("project", "projects", "initiative", "initiatives", "program", "programs", "portfolio"),
    "task": ("task", "tasks", "ticket", "tickets", "work item", "work items", "backlog", "sprint"),
    "decision": ("decision", "decisions", "decided", "decision log", "lessons"),
    "conversation": ("conversation", "conversations", "discussion", "discussions", "thread", "chat", "channel"),
    "message": ("message", "messages", "said", "discussed", "talked", "mentioned", "asking", "asked"),
    "scope": ("scope", "scopes", "department", "departments", "business unit", "division", "team structure"),
    "approval_policy": ("approval", "approvals", "policy", "policies", "approval policy"),
    "goal": ("goal", "goals", "objective", "objectives", "okr", "okrs", "target", "key result"),
    "budget": ("budget", "budgets", "finance", "financial", "spend", "spending", "cost", "costs", "expense"),
    "employee": ("employee", "employees", "who", "people", "person", "member", "staff", "colleague", "team"),
    # Slice 4D.2 — knowledge intent so /brain/answer can cite knowledge evidence
    "knowledge": (
        "document", "documents", "wiki", "wikis", "wiki page",
        "policy", "policies", "sop", "sops", "template", "templates",
        "knowledge", "kb", "guideline", "guidelines", "runbook", "runbooks",
    ),
}

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "of", "for", "in", "on", "at", "to", "from", "with",
        "what", "how", "who", "which", "when", "where", "why", "is", "are",
        "was", "were", "and", "or", "do", "does", "did", "about", "our", "us",
        "my", "me", "their", "there", "its", "it", "we", "they", "them", "all",
        "any", "can", "please", "tell", "show", "list", "summarize", "status",
        "current", "currently", "right", "now", "have", "has", "had", "be",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> str:
    return (value or _utcnow()).isoformat()


def tokens(text: Optional[str]) -> set[str]:
    """Deterministic token set — the only matcher used in this slice."""
    if not text:
        return set()
    raw = _TOKEN_RE.findall(str(text).lower())
    return {t for t in raw if len(t) > 1 and t not in _STOPWORDS}


def classify_query(query: str) -> dict[str, list[str]]:
    """Return evidence types the query refers to, with matched intent tokens."""
    q_tokens = tokens(query)
    if not q_tokens:
        return {}
    matched: dict[str, list[str]] = {}
    for etype, keywords in _INTENT_KEYWORDS.items():
        hits = [kw for kw in keywords if any(kw == t or kw in query.lower() for t in q_tokens)]
        if hits:
            matched[etype] = hits
    return matched


@dataclass
class CallerAccess:
    """Resolved governance visibility for one caller (bounded resolution)."""

    organization_id: str
    user_id: str
    employee_id: Optional[str]
    org_wide: bool = False
    anchored_scope_ids: frozenset[str] = frozenset()
    ancestry_scope_ids: frozenset[str] = frozenset()
    visible_scope_ids: frozenset[str] = frozenset()
    # project ids wrapped by visible project-type scopes (scope.entity_id)
    project_ids: frozenset[str] = frozenset()
    # conversation ids the caller is a member of (empty -> not resolvable)
    member_conversation_ids: frozenset[str] = frozenset()
    links: dict[str, str] = field(default_factory=dict)  # entity_id -> scope_id


async def _load_scope_tree(db: AsyncSession, organization_id: str) -> list[GovernanceScope]:
    rows = (
        await db.execute(
            select(GovernanceScope)
            .where(GovernanceScope.organization_id == organization_id)
            .order_by(GovernanceScope.depth.asc())
            .limit(MAX_SCOPE_NODES)
        )
    ).scalars().all()
    return list(rows)


async def _descendant_scope_ids(
    db: AsyncSession, organization_id: str, anchored: set[str], tree: list[GovernanceScope]
) -> set[str]:
    children: dict[str, list[str]] = {}
    for scope in tree:
        if scope.parent_id:
            children.setdefault(scope.parent_id, []).append(scope.id)
    visible: set[str] = set()
    queue = list(anchored)
    guard = 0
    while queue and guard < MAX_SCOPE_NODES:
        current = queue.pop(0)
        if current in visible:
            continue
        visible.add(current)
        guard += 1
        queue.extend(children.get(current, []))
    return visible


async def resolve_caller_access(
    db: AsyncSession, *, organization_id: str, user: Any
) -> CallerAccess:
    """caller -> user -> organization -> roles -> scopes (bounded, no scans)."""
    employee_id: Optional[str] = None
    employee = (
        await db.execute(
            select(Employee.id).where(
                Employee.organization_id == organization_id,
                Employee.user_id == user.id,
            )
        )
    ).scalars().first()
    if employee:
        employee_id = employee

    assignments = await governance_service.list_assignments(
        db, organization_id=organization_id, user_id=user.id
    )
    org_wide = any(a.scope_id is None for a in assignments)
    anchored = {a.scope_id for a in assignments if a.scope_id}

    tree = await _load_scope_tree(db, organization_id)
    links = {s.entity_id: s.id for s in tree if s.entity_id}
    project_scope_ids = {
        s.id for s in tree if s.scope_type == "project" and s.entity_id
    }
    if org_wide:
        return CallerAccess(
            organization_id=organization_id,
            user_id=user.id,
            employee_id=employee_id,
            org_wide=True,
            anchored_scope_ids=frozenset(anchored),
            ancestry_scope_ids=frozenset(anchored),
            visible_scope_ids=frozenset(s.id for s in tree),
            project_ids=frozenset(s.entity_id for s in tree if s.entity_id),
            member_conversation_ids=await _member_conversation_ids(db, organization_id, employee_id),
            links=links,
        )

    ancestry: set[str] = set()
    for scope_id in anchored:
        ancestry.update(
            await governance_service.ancestor_scope_ids(
                db, organization_id=organization_id, scope_id=scope_id
            )
        )
    visible = await _descendant_scope_ids(db, organization_id, set(anchored), tree)
    project_ids = {s.entity_id for s in tree if s.id in visible and s.scope_type == "project" and s.entity_id}
    return CallerAccess(
        organization_id=organization_id,
        user_id=user.id,
        employee_id=employee_id,
        org_wide=False,
        anchored_scope_ids=frozenset(anchored),
        ancestry_scope_ids=frozenset(ancestry),
        visible_scope_ids=frozenset(visible),
        project_ids=frozenset(project_ids),
        member_conversation_ids=await _member_conversation_ids(db, organization_id, employee_id),
        links=links,
    )


async def _member_conversation_ids(
    db: AsyncSession, organization_id: str, employee_id: Optional[str]
) -> frozenset[str]:
    if not employee_id:
        return frozenset()
    rows = (
        await db.execute(
            select(ConversationMember.conversation_id).where(
                ConversationMember.organization_id == organization_id,
                ConversationMember.employee_id == employee_id,
            )
        )
    ).scalars().all()
    return frozenset(rows)


def _evidence(
    etype: str,
    row: Any,
    *,
    relation: str,
    scope_id: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    meta = _EVIDENCE_META[etype]
    url = meta["url"].format(row.id)
    title: str = row.id
    for attr in ("name", "title", "display_name"):
        value = getattr(row, attr, None)
        if value:
            title = str(value)
            break
    timestamp = getattr(row, "updated_at", None) or getattr(row, "created_at", None)
    item: dict[str, Any] = {
        "type": etype,
        "id": row.id,
        "title": title,
        "url": url,
        "timestamp": _iso(timestamp),
        "relation": relation,
        "source": meta["source"],
    }
    if scope_id:
        item["scope_id"] = scope_id
    if extra:
        item.update(extra)
    return item


def _overlap(hay: str, needles: set[str]) -> bool:
    if not needles:
        return False
    hay_tokens = tokens(hay)
    return bool(hay_tokens & needles)


async def _match_projects(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Project)
            .where(Project.organization_id == access.organization_id)
            .order_by(Project.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not access.org_wide and row.id not in access.project_ids:
            continue
        scope_id = access.links.get(row.id)
        if _overlap(f"{row.name} {row.code}", needles):
            items.append(
                _evidence("project", row, relation="matched", scope_id=scope_id,
                          extra={"detail": f"{row.status} · {row.progress}% progress"})
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            if access.org_wide or row.id in access.project_ids:
                items.append(
                    _evidence("project", row, relation="recent", scope_id=access.links.get(row.id),
                              extra={"detail": f"{row.status} · {row.progress}% progress"})
                )
    return items


async def _match_tasks(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Task)
            .where(Task.organization_id == access.organization_id)
            .order_by(Task.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not access.org_wide and (row.project_id is None or row.project_id not in access.project_ids):
            continue
        if _overlap(f"{row.title} {row.status}", needles):
            items.append(
                _evidence("task", row, relation="matched", extra={
                    "project_id": row.project_id,
                    "detail": f"{row.status} · priority {row.priority}",
                })
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            if access.org_wide or (row.project_id and row.project_id in access.project_ids):
                items.append(
                    _evidence("task", row, relation="recent", extra={
                        "project_id": row.project_id,
                        "detail": f"{row.status} · priority {row.priority}",
                    })
                )
    return items


async def _match_decisions(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Decision)
            .where(Decision.organization_id == access.organization_id)
            .order_by(Decision.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not access.org_wide and (row.project_id is None or row.project_id not in access.project_ids):
            continue
        if _overlap(f"{row.title} {row.status} {row.keywords or ''}", needles):
            items.append(
                _evidence("decision", row, relation="matched", extra={
                    "project_id": row.project_id, "detail": row.status,
                })
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            if access.org_wide or (row.project_id and row.project_id in access.project_ids):
                items.append(
                    _evidence("decision", row, relation="recent", extra={
                        "project_id": row.project_id, "detail": row.status,
                    })
                )
    return items


async def _match_conversations(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    # Conversation evidence is membership-gated for every caller: the brain
    # only cites conversations the caller is a member of (matches messaging 4B
    # semantics where conversations are only visible to their members).
    if not access.member_conversation_ids:
        return []
    stmt = (
        select(Conversation)
        .where(
            Conversation.organization_id == access.organization_id,
            Conversation.id.in_(access.member_conversation_ids),
        )
        .order_by(Conversation.updated_at.desc())
        .limit(MAX_CANDIDATES_PER_TYPE)
    )
    rows = (await db.execute(stmt)).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if row.is_archived:
            continue
        title = row.title or row.channel_key or f"{row.type} conversation"
        if _overlap(f"{title} {row.type}", needles):
            items.append(
                _evidence("conversation", row, relation="matched",
                          extra={"detail": f"{row.type} · {row.message_count} messages"})
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            if not row.is_archived:
                items.append(
                    _evidence("conversation", row, relation="recent",
                              extra={"detail": f"{row.type} · {row.message_count} messages"})
                )
    return items


async def _match_messages(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    # Message evidence is membership-gated for every caller (see above).
    if not access.member_conversation_ids:
        return []
    conversation_ids = list(access.member_conversation_ids)[:MAX_CANDIDATES_PER_TYPE]
    rows = (
        await db.execute(
            select(Message)
            .where(
                Message.organization_id == access.organization_id,
                Message.conversation_id.in_(conversation_ids),
                Message.deleted.is_(False),
            )
            .order_by(Message.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if _overlap(row.content or "", needles):
            items.append(
                _evidence("message", row, relation="matched", extra={
                    "conversation_id": row.conversation_id,
                    "detail": (row.content or "")[:200],
                })
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            items.append(
                _evidence("message", row, relation="recent", extra={
                    "conversation_id": row.conversation_id,
                    "detail": (row.content or "")[:200],
                })
            )
    return items


async def _match_scopes(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    tree = await _load_scope_tree(db, access.organization_id)
    items: list[dict[str, Any]] = []
    for scope in tree:
        if not access.org_wide and scope.id not in access.visible_scope_ids:
            continue
        if _overlap(f"{scope.name} {scope.scope_type}", needles):
            items.append(
                _evidence("scope", scope, relation="matched", scope_id=scope.id,
                          extra={"detail": scope.scope_type})
            )
    if not items and with_recent:
        for scope in tree[:FALLBACK_RECENT_PER_TYPE]:
            if access.org_wide or scope.id in access.visible_scope_ids:
                items.append(
                    _evidence("scope", scope, relation="recent", scope_id=scope.id,
                              extra={"detail": scope.scope_type})
                )
    return items


async def _match_policies(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ApprovalPolicy)
            .where(ApprovalPolicy.organization_id == access.organization_id)
            .order_by(ApprovalPolicy.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not access.org_wide and (row.scope_id is None or row.scope_id not in access.visible_scope_ids):
            continue
        if _overlap(f"{row.name} {row.approval_type}", needles):
            items.append(
                _evidence("approval_policy", row, relation="matched", scope_id=row.scope_id,
                          extra={"detail": f"{row.approval_type} · requires {row.required_permission}"})
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            if access.org_wide or (row.scope_id and row.scope_id in access.visible_scope_ids):
                items.append(
                    _evidence("approval_policy", row, relation="recent", scope_id=row.scope_id,
                              extra={"detail": f"{row.approval_type} · requires {row.required_permission}"})
                )
    return items


async def _match_goals(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Goal)
            .where(Goal.organization_id == access.organization_id)
            .order_by(Goal.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not access.org_wide and (row.project_id is None or row.project_id not in access.project_ids):
            continue
        if _overlap(f"{row.name} {row.status}", needles):
            items.append(
                _evidence("goal", row, relation="matched", extra={
                    "project_id": row.project_id,
                    "detail": f"{row.status} · {row.progress}% progress",
                })
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            if access.org_wide or (row.project_id and row.project_id in access.project_ids):
                items.append(
                    _evidence("goal", row, relation="recent", extra={
                        "project_id": row.project_id,
                        "detail": f"{row.status} · {row.progress}% progress",
                    })
                )
    return items


async def _match_budgets(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Budget)
            .where(Budget.organization_id == access.organization_id)
            .order_by(Budget.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not access.org_wide and (row.project_id is None or row.project_id not in access.project_ids):
            continue
        if _overlap(f"{row.name} {row.budget_type} {row.status}", needles):
            items.append(
                _evidence("budget", row, relation="matched", extra={
                    "project_id": row.project_id,
                    "detail": f"{row.status} · {row.used_amount or 0:.2f} of {row.allocated_amount or 0:.2f} {row.currency or 'USD'} used",
                })
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            if access.org_wide or (row.project_id and row.project_id in access.project_ids):
                items.append(
                    _evidence("budget", row, relation="recent", extra={
                        "project_id": row.project_id,
                        "detail": f"{row.status} · {row.used_amount or 0:.2f} of {row.allocated_amount or 0:.2f} {row.currency or 'USD'} used",
                    })
                )
    return items


async def _match_employees(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    if not access.org_wide:
        return []
    rows = (
        await db.execute(
            select(Employee)
            .where(Employee.organization_id == access.organization_id)
            .order_by(Employee.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if _overlap(f"{row.display_name or ''} {row.first_name} {row.last_name or ''} {row.email} {row.designation or ''}", needles):
            items.append(
                _evidence("employee", row, relation="matched",
                          extra={"detail": row.designation or "employee"})
            )
    return items


def _knowledge_visible(access: CallerAccess, row: Any) -> bool:
    """Downward-only knowledge visibility (bounded, project-anchored)."""
    if access.org_wide:
        return True
    project_id = getattr(row, "project_id", None)
    return project_id is not None and project_id in access.project_ids


async def _match_knowledge_kind(
    db: AsyncSession,
    access: CallerAccess,
    needles: set[str],
    *,
    with_recent: bool,
    kind: str,
    model: Any,
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(model)
            .where(
                model.organization_id == access.organization_id,
                model.status.in_(KNOWLEDGE_PUBLISHED),
            )
            .order_by(model.updated_at.desc())
            .limit(MAX_CANDIDATES_PER_TYPE)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not _knowledge_visible(access, row):
            continue
        if _overlap(f"{row.title} {row.category or ''} {row.status}", needles):
            items.append(
                _evidence(kind, row, relation="matched", extra={
                    "project_id": getattr(row, "project_id", None),
                    "detail": row.status,
                })
            )
    if not items and with_recent:
        for row in rows[:FALLBACK_RECENT_PER_TYPE]:
            if not _knowledge_visible(access, row):
                continue
            items.append(
                _evidence(kind, row, relation="recent", extra={
                    "project_id": getattr(row, "project_id", None),
                    "detail": row.status,
                })
            )
    return items


_KNOWLEDGE_MODELS = {
    "document": "Document",
    "wiki": "WikiPage",
    "policy": "Policy",
    "sop": "SOP",
    "template": "Template",
}


def _knowledge_matcher(kind: str, model: Any):
    return partial(_match_knowledge_kind, kind=kind, model=model)


async def _match_knowledge(
    db: AsyncSession, access: CallerAccess, needles: set[str], *, with_recent: bool
) -> list[dict[str, Any]]:
    """Aggregate knowledge matcher for the ``knowledge`` intent."""
    items: list[dict[str, Any]] = []
    for kind in KNOWLEDGE_EVIDENCE_KINDS:
        items.extend(await _MATCHERS[kind](db, access, needles, with_recent=with_recent))
    return items


_MATCHERS = {
    "project": _match_projects,
    "task": _match_tasks,
    "decision": _match_decisions,
    "conversation": _match_conversations,
    "message": _match_messages,
    "scope": _match_scopes,
    "approval_policy": _match_policies,
    "goal": _match_goals,
    "budget": _match_budgets,
    "employee": _match_employees,
}

for _kind in KNOWLEDGE_EVIDENCE_KINDS:
    _module = __import__("app.models.knowledge", fromlist=[_KNOWLEDGE_MODELS[_kind]])
    _MATCHERS[_kind] = _knowledge_matcher(_kind, getattr(_module, _KNOWLEDGE_MODELS[_kind]))
_MATCHERS["knowledge"] = _match_knowledge


def _relations(evidence: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[tuple[str, str], dict[str, Any]] = {}
    for item in evidence:
        by_id[(item["type"], item["id"])] = item
    relations: list[dict[str, Any]] = []
    for link in extra:
        src_type, src_id = link["source"]
        tgt_type, tgt_id = link["target"]
        if (src_type, src_id) in by_id and (tgt_type, tgt_id) in by_id:
            relations.append(
                {"source": {"type": src_type, "id": src_id},
                 "target": {"type": tgt_type, "id": tgt_id},
                 "kind": link["kind"]}
            )
    return relations


async def _direct_evidence(
    db: AsyncSession,
    access: CallerAccess,
    *,
    entity_type: str,
    entity_id: str,
) -> list[dict[str, Any]]:
    if entity_type not in _EVIDENCE_META:
        return []
    model_map = {
        "project": Project, "task": Task, "decision": Decision,
        "conversation": Conversation, "message": Message,
        "scope": GovernanceScope, "approval_policy": ApprovalPolicy,
        "goal": Goal, "budget": Budget, "employee": Employee,
    }
    for kind in KNOWLEDGE_EVIDENCE_KINDS:
        model_map[kind] = getattr(
            __import__("app.models.knowledge", fromlist=[_KNOWLEDGE_MODELS[kind]]),
            _KNOWLEDGE_MODELS[kind],
        )
    model = model_map.get(entity_type)
    if model is None:
        return []
    row = (
        await db.execute(
            select(model).where(
                model.organization_id == access.organization_id,
                model.id == entity_id,
            )
        )
    ).scalars().first()
    if row is None:
        return []
    if entity_type == "scope" and not access.org_wide and row.id not in access.visible_scope_ids:
        return []
    if entity_type == "approval_policy" and not access.org_wide and (
        row.scope_id is None or row.scope_id not in access.visible_scope_ids
    ):
        return []
    if entity_type in ("project",) and not access.org_wide and row.id not in access.project_ids:
        return []
    if entity_type in ("task", "decision", "goal", "budget"):
        project_id = getattr(row, "project_id", None)
        if not access.org_wide and (project_id is None or project_id not in access.project_ids):
            return []
    if entity_type in ("conversation", "message"):
        if not access.org_wide:
            target_conv = row.conversation_id if entity_type == "message" else row.id
            if target_conv not in access.member_conversation_ids:
                return []
    if entity_type == "employee" and not access.org_wide:
        return []
    if entity_type in KNOWLEDGE_EVIDENCE_KINDS and not _knowledge_visible(access, row):
        return []
    scope_id = None
    if entity_type == "scope":
        scope_id = row.id
    elif entity_type == "approval_policy":
        scope_id = row.scope_id
    return [_evidence(entity_type, row, relation="direct", scope_id=scope_id)]


async def build_context(
    db: AsyncSession,
    user: Any,
    query: str,
    *,
    organization_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = DEFAULT_CONTEXT_LIMIT,
) -> dict[str, Any]:
    """Governance-scoped context for a question (the canonical entry point).

    Returns a bounded context::

        {
          "scope_ids": [...],          # scopes the caller may see
          "org_wide": bool,
          "evidence": [EvidenceItem],
          "relations": [...],
          "entity_mentions": {type: [ids]},
          "truncated": bool,
        }
    """
    if not query.strip():
        query = "company overview"
    access = await resolve_caller_access(
        db, organization_id=organization_id, user=user
    )
    intent = classify_query(query)
    evidence: list[dict[str, Any]] = []
    extra_links: list[dict[str, Any]] = []
    mentions: dict[str, list[str]] = {}
    for etype, needles_words in intent.items():
        needles = tokens(" ".join(needles_words)) or tokens(query)
        items = await _MATCHERS[etype](
            db, access, needles, with_recent=True
        )
        for item in items:
            mentions.setdefault(item["type"], []).append(item["id"])
        evidence.extend(items)

    if entity_type and entity_id:
        direct = await _direct_evidence(
            db, access, entity_type=entity_type, entity_id=entity_id
        )
        for item in direct:
            mentions.setdefault(item["type"], []).append(item["id"])
        evidence = direct + evidence

    for item in evidence:
        if item["type"] == "task" and item["relation"] == "matched":
            extra_links.append(
                {"source": ("task", item["id"]), "target": ("project", item["project_id"]), "kind": "belongs_to"}
            )
        if item["type"] == "decision" and item["relation"] == "matched":
            extra_links.append(
                {"source": ("decision", item["id"]), "target": ("project", item["project_id"]), "kind": "belongs_to"}
            )
        if item["type"] == "message" and item["relation"] == "matched":
            extra_links.append(
                {"source": ("message", item["id"]), "target": ("conversation", item["conversation_id"]), "kind": "belongs_to"}
            )
        if item["type"] == "budget" and item["relation"] == "matched":
            extra_links.append(
                {"source": ("budget", item["id"]), "target": ("project", item["project_id"]), "kind": "belongs_to"}
            )
        if item["type"] == "goal" and item["relation"] == "matched":
            extra_links.append(
                {"source": ("goal", item["id"]), "target": ("project", item["project_id"]), "kind": "belongs_to"}
            )
    evidence = evidence[:limit]
    truncated = len(evidence) >= limit
    relations = _relations(evidence, extra_links)
    scope_ids = sorted(
        set(access.visible_scope_ids) | set(access.ancestry_scope_ids) | set(access.anchored_scope_ids)
    )
    return {
        "scope_ids": scope_ids,
        "org_wide": access.org_wide,
        "evidence": evidence,
        "relations": relations,
        "entity_mentions": mentions,
        "truncated": truncated,
    }


async def resolve_accessible_ids(
    db: AsyncSession,
    user: Any,
    *,
    organization_id: str,
    kind: str,
    ids: list[str],
) -> list[str]:
    """Return the subset of ``ids`` the caller may access (search filtering).

    Bounded: at most MAX_RESOLVE_IDS input ids, one indexed org-scoped fetch.
    """
    if not ids or kind not in _EVIDENCE_META:
        return []
    ids = list(dict.fromkeys(ids))[:MAX_RESOLVE_IDS]
    access = await resolve_caller_access(db, organization_id=organization_id, user=user)
    if kind in ("conversation", "message"):
        # Conversation/message access is membership-gated for every caller.
        visible = set(await _conversation_ids(db, access)) if kind == "conversation" else set(
            await _message_ids(db, access)
        )
    elif access.org_wide:
        model_map = {
            "project": Project, "task": Task, "decision": Decision,
            "conversation": Conversation, "message": Message,
            "scope": GovernanceScope, "approval_policy": ApprovalPolicy,
            "goal": Goal, "budget": Budget, "employee": Employee,
        }
        for _kind in KNOWLEDGE_EVIDENCE_KINDS:
            model_map[_kind] = getattr(
                __import__("app.models.knowledge", fromlist=[_KNOWLEDGE_MODELS[_kind]]),
                _KNOWLEDGE_MODELS[_kind],
            )
        model = model_map[kind]
        rows = (
            await db.execute(
                select(model.id).where(
                    model.organization_id == organization_id,
                    model.id.in_(ids),
                )
            )
        ).scalars().all()
        visible = set(rows)
    else:
        visible = await _filter_scope_anchored(
            db, access, kind=kind, ids=ids
        )
    return [i for i in ids if i in visible]


async def _conversation_ids(db: AsyncSession, access: CallerAccess) -> list[str]:
    if not access.member_conversation_ids:
        return []
    rows = (
        await db.execute(
            select(Conversation.id).where(
                Conversation.organization_id == access.organization_id,
                Conversation.id.in_(access.member_conversation_ids),
            )
        )
    ).scalars().all()
    return list(rows)


async def _message_ids(db: AsyncSession, access: CallerAccess) -> list[str]:
    if not access.member_conversation_ids:
        return []
    rows = (
        await db.execute(
            select(Message.id).where(
                Message.organization_id == access.organization_id,
                Message.deleted.is_(False),
                Message.conversation_id.in_(access.member_conversation_ids),
            )
        )
    ).scalars().all()
    return list(rows)


async def _filter_scope_anchored(
    db: AsyncSession, access: CallerAccess, *, kind: str, ids: list[str]
) -> set[str]:
    visible: set[str] = set()
    if kind == "scope":
        visible = {i for i in ids if i in access.visible_scope_ids}
    elif kind == "approval_policy":
        rows = (
            await db.execute(
                select(ApprovalPolicy.id, ApprovalPolicy.scope_id).where(
                    ApprovalPolicy.organization_id == access.organization_id,
                    ApprovalPolicy.id.in_(ids),
                )
            )
        ).all()
        visible = {
            row.id for row in rows
            if row.scope_id and row.scope_id in access.visible_scope_ids
        }
    elif kind in ("project", "task", "decision", "goal", "budget"):
        if kind == "project":
            rows = (
                await db.execute(
                    select(Project.id).where(
                        Project.organization_id == access.organization_id,
                        Project.id.in_(ids),
                    )
                )
            ).scalars().all()
            visible = {row for row in rows if row in access.project_ids}
        elif kind == "task":
            rows = (
                await db.execute(
                    select(Task.id, Task.project_id).where(
                        Task.organization_id == access.organization_id,
                        Task.id.in_(ids),
                    )
                )
            ).all()
            visible = {
                row.id for row in rows
                if row.project_id and row.project_id in access.project_ids
            }
        elif kind == "decision":
            rows = (
                await db.execute(
                    select(Decision.id, Decision.project_id).where(
                        Decision.organization_id == access.organization_id,
                        Decision.id.in_(ids),
                    )
                )
            ).all()
            visible = {
                row.id for row in rows
                if row.project_id and row.project_id in access.project_ids
            }
        elif kind == "goal":
            rows = (
                await db.execute(
                    select(Goal.id, Goal.project_id).where(
                        Goal.organization_id == access.organization_id,
                        Goal.id.in_(ids),
                    )
                )
            ).all()
            visible = {
                row.id for row in rows
                if row.project_id and row.project_id in access.project_ids
            }
        else:
            rows = (
                await db.execute(
                    select(Budget.id, Budget.project_id).where(
                        Budget.organization_id == access.organization_id,
                        Budget.id.in_(ids),
                    )
                )
            ).all()
            visible = {
                row.id for row in rows
                if row.project_id and row.project_id in access.project_ids
            }
    elif kind in KNOWLEDGE_EVIDENCE_KINDS:
        if kind in ("policy", "sop", "template"):
            # No project anchor: visible to org-wide callers only.
            return set()
        model = getattr(
            __import__("app.models.knowledge", fromlist=[_KNOWLEDGE_MODELS[kind]]),
            _KNOWLEDGE_MODELS[kind],
        )
        rows = (
            await db.execute(
                select(model.id, model.project_id).where(
                    model.organization_id == access.organization_id,
                    model.id.in_(ids),
                )
            )
        ).all()
        visible = {
            row.id for row in rows
            if row.project_id and row.project_id in access.project_ids
        }
    elif kind in ("conversation", "message"):
        if not access.member_conversation_ids:
            return set()
        if kind == "conversation":
            rows = (
                await db.execute(
                    select(Conversation.id).where(
                        Conversation.organization_id == access.organization_id,
                        Conversation.id.in_(ids),
                        Conversation.id.in_(access.member_conversation_ids),
                    )
                )
            ).scalars().all()
            visible = set(rows)
        else:
            rows = (
                await db.execute(
                    select(Message.id, Message.conversation_id).where(
                        Message.organization_id == access.organization_id,
                        Message.id.in_(ids),
                        Message.deleted.is_(False),
                    )
                )
            ).all()
            visible = {
                row.id for row in rows
                if row.conversation_id in access.member_conversation_ids
            }
    return visible
