"""Deterministic, idempotent demo-company seeder (go-live deliverable).

Seeds a fictional company ("Nova Labs Demo") with departments, employees,
projects, tasks and a decision history so that any visitor can experience
VCOS â€” including the Truth Center â€” without configuring an organization.

Canonical-path guarantee:
  * Every entity is created through the product's own public API (the same
    endpoints a real user calls), so canonical mutation, governance,
    provenance and tenant rules all apply.
  * The one demo contradiction is written by calling the ratified engine's
    own exact-once writer `company_operating_engine.surface_contradictions`
    (the same function the production event pipeline uses) â€” never a raw
    insert into the contradictions table.

Usage:
    python -m app.demo_company            # seed via HTTP API
    python -m app.demo_company --with-db  # also seed the contradiction row

Environment (all optional):
    DEMO_API_BASE_URL       default http://127.0.0.1:8999
    DEMO_ADMIN_EMAIL        default demo.admin@novalabs-demo.com
    DEMO_ADMIN_PASSWORD     default Demo-Password-2026!
    DEMO_ORG_NAME           default Nova Labs Demo
    DEMO_ORG_SLUG           default nova-labs-demo
    DEMO_ALLOW_PRODUCTION   must be "1" to run against a production backend

Safety: refuses to run against a production environment unless explicitly
overridden; always targets only the dedicated demo organization slug.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

API_BASE = os.getenv("DEMO_API_BASE_URL", "http://127.0.0.1:8999").rstrip("/")
ADMIN_EMAIL = os.getenv("DEMO_ADMIN_EMAIL", "demo.admin@novalabs-demo.com")
ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "Demo-Password-2026!")
ORG_NAME = os.getenv("DEMO_ORG_NAME", "Nova Labs Demo")
ORG_SLUG = os.getenv("DEMO_ORG_SLUG", "nova-labs-demo")

MARKER = "DEMO:"
CANONICAL_DECISION_ID = "demo-dec-apollo-001"


class DemoApi:
    def __init__(self, base: str) -> None:
        self.base = base
        self.token: str | None = None
        self.results: list[str] = []

    def request(self, method: str, path: str, body: dict | None = None, auth: bool = True):
        url = f"{self.base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if auth and self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"detail": raw[:300]}
            return exc.code, payload

    # --- steps -----------------------------------------------------------

    def guard_environment(self) -> bool:
        status, platform = self.request("GET", "/api/v1/platform", auth=False)
        env = platform.get("environment", "?") if status == 200 else "unreachable"
        print(f"target API:   {self.base}")
        print(f"environment:  {env}")
        if env == "production" and os.getenv("DEMO_ALLOW_PRODUCTION") != "1":
            print("REFUSING: target is production. Set DEMO_ALLOW_PRODUCTION=1 to override.")
            return False
        return status == 200

    def authenticate(self) -> bool:
        status, data = self.request(
            "POST", "/api/v1/auth/login",
            {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, auth=False,
        )
        if status == 200:
            token = data.get("access_token") or data.get("token")
            if token:
                self.token = token
                self.results.append("login: existing demo admin")
                return True
        status, data = self.request(
            "POST", "/api/v1/auth/register",
            {
                "organization_name": ORG_NAME,
                "organization_slug": ORG_SLUG,
                "industry": "Software",
                "country": "United States",
                "timezone": "UTC",
                "currency": "USD",
                "full_name": "Demo Admin",
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
            },
            auth=False,
        )
        if status in (200, 201):
            token = data.get("access_token") or data.get("token")
            if not token:
                # register may require a separate login
                status, data = self.request(
                    "POST", "/api/v1/auth/login",
                    {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, auth=False,
                )
                token = data.get("access_token") or data.get("token")
            self.token = token
            self.results.append("register: demo organization created")
            return bool(token)
        print(f"FATAL: could not authenticate or register demo admin ({status}): {data}")
        return False

    def _find(self, path: str, params: dict | None = None) -> list:
        query = urllib.parse.urlencode(params) if params else ""
        status, data = self.request("GET", f"{path}?{query}" if query else path)
        return data if isinstance(data, list) else []

    def _ensure(self, label: str, check_path: str, params: dict | None,
                match, create_path: str, payload: dict) -> dict:
        for row in self._find(check_path, params):
            if isinstance(row, dict) and match(row):
                self.results.append(f"exists {label}")
                return row
        return self._create(label, create_path, payload) or {}

    def _create(self, label: str, path: str, payload: dict) -> dict | None:
        status, data = self.request("POST", path, payload)
        if status in (200, 201):
            self.results.append(f"created {label}")
            return data if isinstance(data, dict) else {}
        self.results.append(f"SKIPPED {label} ({status}): {str(data)[:120]}")
        return None

    def seed_company(self, link_decision: str | None = None) -> None:
        today = date.today()

        eng = self._ensure(
            "department Engineering", "/api/v1/departments", None,
            lambda r: r.get("code") == "demo-eng", "/api/v1/departments",
            {"name": "Engineering", "code": "demo-eng",
             "description": "Product engineering"})
        prd = self._ensure(
            "department Product", "/api/v1/departments", None,
            lambda r: r.get("code") == "demo-prd", "/api/v1/departments",
            {"name": "Product", "code": "demo-prd",
             "description": "Product management"})
        dept_id = eng.get("id")

        alice = self._ensure(
            "employee Alice Chen", "/api/v1/employees", {"limit": 100},
            lambda r: r.get("email") == "alice.chen@novalabs-demo.com", "/api/v1/employees",
            {"first_name": "Alice", "last_name": "Chen",
             "email": "alice.chen@novalabs-demo.com",
             "designation": "Staff Engineer",
             "department_id": dept_id, "employment_type": "full_time"})
        bob = self._ensure(
            "employee Bob Rivera", "/api/v1/employees", {"limit": 100},
            lambda r: r.get("email") == "bob.rivera@novalabs-demo.com", "/api/v1/employees",
            {"first_name": "Bob", "last_name": "Rivera",
             "email": "bob.rivera@novalabs-demo.com",
             "designation": "Product Manager",
             "department_id": prd.get("id"),
             "employment_type": "full_time"})
        carol = self._ensure(
            "employee Carol Okafor", "/api/v1/employees", {"limit": 100},
            lambda r: r.get("email") == "carol.okafor@novalabs-demo.com", "/api/v1/employees",
            {"first_name": "Carol", "last_name": "Okafor",
             "email": "carol.okafor@novalabs-demo.com",
             "designation": "Data Engineer",
             "department_id": dept_id, "employment_type": "full_time"})

        project = self._ensure(
            "project Apollo Platform", "/api/v1/projects", {"limit": 100},
            lambda r: r.get("code") == "DEMO-APOLLO", "/api/v1/projects",
            {"name": f"{MARKER} Apollo Platform",
             "code": "DEMO-APOLLO",
             "description": "Customer data platform rebuild.",
             "status": "active", "priority": "high",
             "department_id": dept_id})
        project_id = project.get("id")

        def task_ensure(label, title, description, status, priority, assignee, due):
            return self._ensure(
                label, "/api/v1/tasks", {"limit": 100},
                lambda r: r.get("title") == title, "/api/v1/tasks",
                {"title": title, "description": description,
                 "project_id": project_id, "status": status,
                 "priority": priority, "assignee_id": assignee,
                 "due_date": due.isoformat()})

        task_ensure("task integration spike",
                    f"{MARKER} Finish vendor integration spike",
                    "Evaluate the vendor API for the platform.",
                    "in_progress", "high", alice.get("id"), today + timedelta(days=3))
        task_ensure("task overdue dependency",
                    f"{MARKER} Resolve overdue data-sync dependency",
                    "Upstream team has not delivered the schema.",
                    "blocked", "critical", carol.get("id"), today - timedelta(days=5))
        task_ensure("task roadmap review",
                    f"{MARKER} Q3 roadmap review",
                    "Review roadmap against customer commitments.",
                    "todo", "medium", bob.get("id"), today + timedelta(days=10))

        def decision_ensure(label, title, description, status, summary):
            return self._ensure(
                label, "/api/v1/decisions", {"search": "DEMO", "limit": 100},
                lambda r: r.get("title") == title, "/api/v1/decisions",
                {"title": title, "description": description,
                 "status": status, "project_id": project_id,
                 "summary": summary})

        decision_ensure("decision platform rewrite",
                        f"{MARKER} Proceed with Apollo platform rewrite",
                        "Rewrite the platform on the new architecture.",
                        "made", "Approved after architecture review.")
        decision_ensure("decision vendor selection",
                        f"{MARKER} Select vendor for data ingestion",
                        "Two vendors evaluated; pricing differs.",
                        "proposed", "Pending final pricing review.")
        decision_ensure("decision hiring plan",
                        f"{MARKER} Approve two data-engineering hires",
                        "Hiring plan for the platform team.",
                        "implemented", "Both roles opened.")

        if link_decision:
            auth = self._ensure(
                "authorization budget", "/api/v1/governed-commitment/authorizations",
                {"limit": 100}, lambda r: str(r.get("title", "")).startswith(MARKER),
                "/api/v1/governed-commitment/authorizations",
                {"authorization_type": "full",
                 "title": f"{MARKER} Authorize platform budget",
                 "description": "Budget authorization for the rewrite.",
                 "decision_id": link_decision})
            if auth.get("id") and auth.get("state") in ("requested", "under_review"):
                status, data = self.request(
                    "POST",
                    f"/api/v1/governed-commitment/authorizations/{auth['id']}/review",
                    {"action": "approve",
                     "review_note": "DEMO: annual budget approved by the executive team."})
                if status == 200:
                    self.results.append("approved authorization budget")
                    auth = data
                else:
                    self.results.append(f"SKIPPED approval ({status}): {str(data)[:120]}")
            self._ensure(
                "commitment delivery deadline", "/api/v1/governed-commitment/commitments",
                {"limit": 100}, lambda r: str(r.get("title", "")).startswith(MARKER),
                "/api/v1/governed-commitment/commitments",
                {"commitment_type": "conditional",
                 "title": f"{MARKER} Deliver Apollo beta by end of quarter",
                 "description": "Commitment made to the executive team.",
                 "decision_id": link_decision,
                 "authorization_id": auth.get("id")})

    async def seed_contradiction(self) -> None:
        """Mint the demo company decision and its contradiction through the
        engine's own canonical writers (record_decision + surface_contradictions).
        Both are exact-once, so reruns are safe."""
        from types import SimpleNamespace

        from sqlalchemy import select

        from app.db.database import SessionLocal
        from app.intelligence.company_operating_engine import company_operating_engine
        from app.models.organization import Organization

        decision_id = CANONICAL_DECISION_ID
        event = SimpleNamespace(id="demo-seed-event", name="demo.seed")
        async with SessionLocal() as db:
            org = (
                await db.execute(select(Organization).where(Organization.slug == ORG_SLUG))
            ).scalar_one_or_none()
            if org is None:
                self.results.append("SKIPPED contradiction (demo org not found in this DB)")
                return
            await company_operating_engine.record_decision(
                db,
                organization_id=org.id,
                event=event,
                payload={
                    "decision_id": decision_id,
                    "kind": "project",
                    "title": f"{MARKER} Proceed to Apollo quarter-end beta with current staffing",
                    "rationale": "DEMO: leadership approved the beta plan based on the weekly status report.",
                    "state": "approved",
                    "owner_label": "Demo COO",
                    "approver_label": "Demo CEO",
                },
            )
            created = await company_operating_engine.surface_contradictions(
                db,
                organization_id=org.id,
                event=event,
                payload={
                    "decision_id": decision_id,
                    "contradiction_index": 1,
                    "side_a": {
                        "claims": ["Apollo is on schedule for the quarter-end beta."],
                        "evidence": ["project status report"],
                        "at": date.today().isoformat(),
                    },
                    "side_b": {
                        "claims": ["A required data-sync dependency is five days overdue; "
                                   "the beta path is blocked."],
                        "evidence": ["overdue task record", "blocked vendor spike"],
                        "at": date.today().isoformat(),
                    },
                },
            )
            await db.commit()
            self.results.append(
                "contradiction created" if created else "contradiction already present (exact-once)"
            )


async def run(with_db: bool) -> int:
    api = DemoApi(API_BASE)
    if not api.guard_environment():
        return 2
    if not api.authenticate():
        return 2

    if with_db:
        await api.seed_contradiction()

    api.seed_company(link_decision=CANONICAL_DECISION_ID if with_db else None)

    print("\n--- demo seed report ---")
    for line in api.results:
        print(f"  {line}")
    print(f"  admin login: {ADMIN_EMAIL}")
    print(f"  organization: {ORG_NAME} ({ORG_SLUG})")
    if not with_db:
        print("  note: run with --with-db to seed the canonical demo contradiction")
    return 1 if any(r.startswith("FATAL") for r in api.results) else 0


if __name__ == "__main__":
    code = asyncio.run(run(with_db="--with-db" in sys.argv))
    raise SystemExit(code)


