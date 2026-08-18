"""Slice 4G.4 — governance: access scoping and write-path validation.

Under test:

* capacity READS (center/gaps/contention/traceability/overloads/detail/
  alternatives/what-if) are org-wide only — a scoped reader gets 404
  "scope not found" BEFORE any engine work happens,
* capacity WRITES (demands + allocations + outcomes) are org-wide managed
  writes — scoped and non-privileged callers are rejected,
* the demand write path validates project existence, capabilities, units,
  proficiency and the window; the allocation path validates the outcome
  taxonomy and the allocation lifecycle,
* the what-if surface needs a real shared demand window,
* hidden people never leak: a scoped caller never receives capacity
  payloads (filtering happens before assembly).
"""

from datetime import date, timedelta

from tests._brain4d6_helpers import invite_scoped_reader
from tests.conftest import register_org

CAP = "/api/v1/brain/execution/capacity"
BRAIN = "/api/v1/brain"


async def _drain(db_session_factory, limit=200, rounds=6):
    from app.events.event_bus import event_bus

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await event_bus.process_pending(session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _project(db_session_factory, org_id, name):
    from app.models.project import Project

    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id, name=name,
            code=f"g4g-{name.lower().replace(' ', '-')[:16]}", status="active",
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    return pid


async def _capability(db_session_factory, org_id, name, available=8):
    from app.models.org_capability_intelligence import OrgCapability

    async with db_session_factory() as db:
        db.add(OrgCapability(
            organization_id=org_id, skill_id=f"sk-{name[:20]}",
            canonical_name=name, capacity_potential=10,
            capacity_committed=2, capacity_reserved=0,
            capacity_available=available, capacity_state="available",
            expert_count=3, evidence_count=3, lifecycle="established",
        ))
        await db.commit()


async def _capability_scope(client, headers, project_id):
    scope = await client.post(
        "/api/v1/governance/scopes",
        json={"name": "4g4 scope", "scope_type": "project",
              "entity_id": project_id},
        headers=headers,
    )
    assert scope.status_code in (200, 201), scope.text
    return scope.json()["id"]


async def _demand_org(client, headers, project_id, capability="security_eng",
                      units=2, days=30):
    ws = date.today()
    we = ws + timedelta(days=days)
    resp = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": capability,
              "units": units, "window_start": ws.isoformat(),
              "window_end": we.isoformat(), "proficiency": "high"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Scoped callers are rejected before any engine work
# ---------------------------------------------------------------------------

async def test_capacity_reads_are_org_wide_only(client, db_session_factory):
    org = await register_org(client, email="4g4_scope@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    project_id = await _project(db_session_factory, org_id, "Scoped Project")
    await _capability(db_session_factory, org_id, "security_eng")
    await _demand_org(client, headers, project_id)
    await _drain(db_session_factory)

    scope_id = await _capability_scope(client, headers, project_id)
    scoped = await invite_scoped_reader(client, headers, scope_id, "4g4scoped@test.co")

    for path in (
        "/execution/capacity/center",
        "/execution/capacity/gaps",
        "/execution/capacity/contention",
        "/execution/capacity/traceability",
        "/execution/capacity/overloads",
        "/execution/capacity/capabilities/security_eng",
        f"/execution/capacity/alternatives?project_id={project_id}",
        f"/execution/capacity/what-if?from_project_id={project_id}"
        f"&to_project_id={project_id}&capability=security_eng&units=1",
    ):
        resp = await client.get(f"{BRAIN}{path}", headers=scoped)
        assert resp.status_code == 404, f"{path} -> {resp.status_code}"
        assert resp.json()["detail"] == "scope not found"

    # and the scoped brain question gets the same honest answer
    ask = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": "which capability is our biggest bottleneck"},
        headers=scoped,
    )
    assert ask.status_code == 200
    body = ask.json()
    assert body["intent"] == "capacity"
    assert body["scope"] == "project"
    assert "your scope does not include it" in body["answer"]


async def test_scoped_caller_never_sees_capacity_payload(client, db_session_factory):
    """Filtering happens before assembly: no engine surface is even called."""
    org = await register_org(client, email="4g4_leak@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    project_id = await _project(db_session_factory, org_id, "Leak Project")
    scope_id = await _capability_scope(client, headers, project_id)
    scoped = await invite_scoped_reader(client, headers, scope_id, "4g4leak@test.co")

    resp = await client.get(f"{BRAIN}/execution/capacity/center", headers=scoped)
    assert resp.status_code == 404
    assert "critical_bottlenecks" not in resp.text
    assert "company_utilization" not in resp.text


# ---------------------------------------------------------------------------
# 2. Write paths are org-wide managed writes
# ---------------------------------------------------------------------------

async def test_capacity_writes_require_org_wide_manage(client, db_session_factory):
    org = await register_org(client, email="4g4_wrt@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    project_id = await _project(db_session_factory, org_id, "Write Project")
    await _capability(db_session_factory, org_id, "security_eng")
    scope_id = await _capability_scope(client, headers, project_id)
    scoped = await invite_scoped_reader(client, headers, scope_id, "4g4wrt@test.co")

    body = {
        "project_id": project_id, "capability": "security_eng", "units": 2,
        "window_start": date.today().isoformat(),
        "window_end": (date.today() + timedelta(days=30)).isoformat(),
    }
    demand = await client.post(f"{CAP}/demands", json=body, headers=scoped)
    assert demand.status_code == 403, demand.text
    allocation = await client.post(f"{CAP}/allocations", json=body, headers=scoped)
    assert allocation.status_code == 403, allocation.text


async def test_writes_without_projects_manage_permission(client, db_session_factory):
    """A read-only reviewer (brain:read delegated, NO role assignment) can
    read the capacity surfaces but gets 403 on every governed write."""
    org = await register_org(client, email="4g4_pmt@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    project_id = await _project(db_session_factory, org_id, "Reader Project")
    await _capability(db_session_factory, org_id, "security_eng")

    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "4g4pmt@test.co", "full_name": "Read Only",
              "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Read Only",
              "password": "B4DPass123!"},
    )
    assert joined.status_code == 201, joined.text
    org_headers = {"Authorization": f"Bearer {joined.json()['access_token']}"}
    user_id = joined.json()["user"]["id"]
    # grant ONLY brain:read via delegation - no role -> no projects:manage
    await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": user_id, "permission_code": "brain:read",
              "reason": "4g4 read-only reviewer"},
        headers=headers,
    )

    body = {
        "project_id": project_id, "capability": "security_eng", "units": 2,
        "window_start": date.today().isoformat(),
        "window_end": (date.today() + timedelta(days=30)).isoformat(),
    }
    demand = await client.post(f"{CAP}/demands", json=body, headers=org_headers)
    assert demand.status_code == 403, demand.text
    allocation = await client.post(
        f"{CAP}/allocations", json=body, headers=org_headers,
    )
    assert allocation.status_code == 403, allocation.text

    # reads stay available to the read-only caller
    center = await client.get(
        f"{BRAIN}/execution/capacity/center", headers=org_headers,
    )
    assert center.status_code == 200, center.text
    assert center.json()["critical_bottlenecks"] == []


# ---------------------------------------------------------------------------
# 3. Demand write-path validation
# ---------------------------------------------------------------------------

async def test_demand_write_path_validation(client, db_session_factory):
    org = await register_org(client, email="4g4_val@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws = date.today()
    we = ws + timedelta(days=30)
    project_id = await _project(db_session_factory, org_id, "Valid Project")
    await _capability(db_session_factory, org_id, "security_eng")

    missing_project = await client.post(
        f"{CAP}/demands",
        json={"project_id": "nope", "capability": "security_eng", "units": 1,
              "window_start": ws.isoformat(), "window_end": we.isoformat()},
        headers=headers,
    )
    assert missing_project.status_code == 404
    assert missing_project.json()["detail"] == "project not found"

    missing_capability = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "units": 1,
              "window_start": ws.isoformat(), "window_end": we.isoformat()},
        headers=headers,
    )
    assert missing_capability.status_code == 400
    assert missing_capability.json()["detail"] == "capability is required"

    missing_window = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": "security_eng",
              "units": 1},
        headers=headers,
    )
    assert missing_window.status_code == 400
    assert "window_start" in missing_window.json()["detail"]

    inverted = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": "security_eng",
              "units": 1, "window_start": we.isoformat(),
              "window_end": ws.isoformat()},
        headers=headers,
    )
    assert inverted.status_code == 400

    # units are clamped to >= 1 (the governed write never stores zero)
    clamped_small = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": "security_eng",
              "units": 0, "window_start": ws.isoformat(),
              "window_end": we.isoformat()},
        headers=headers,
    )
    assert clamped_small.status_code == 200, clamped_small.text
    clamped_neg = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": "security_eng",
              "units": -3, "window_start": ws.isoformat(),
              "window_end": we.isoformat()},
        headers=headers,
    )
    assert clamped_neg.status_code == 200, clamped_neg.text

    bad_proficiency = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": "security_eng",
              "units": 1, "window_start": ws.isoformat(),
              "window_end": we.isoformat(), "proficiency": "godlike"},
        headers=headers,
    )
    assert bad_proficiency.status_code == 400
    assert bad_proficiency.json()["detail"] == "proficiency must be high or expert"

    unknown_remove = await client.post(
        f"{CAP}/demands/does-not-exist/remove", json={}, headers=headers,
    )
    assert unknown_remove.status_code == 404
    assert unknown_remove.json()["detail"] == "demand not found"

    bad_outcome = await client.post(
        f"{CAP}/allocations/does-not-exist/outcome",
        json={"outcome": "magical"}, headers=headers,
    )
    assert bad_outcome.status_code == 404
    assert bad_outcome.json()["detail"] == "allocation not found"


async def test_allocation_outcome_lifecycle_validation(client, db_session_factory):
    org = await register_org(client, email="4g4_alloc@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws = date.today()
    we = ws + timedelta(days=30)
    project_id = await _project(db_session_factory, org_id, "Alloc Project")

    created = await client.post(
        f"{CAP}/allocations",
        json={"project_id": project_id, "capability": "security_eng",
              "units": 2, "window_start": ws.isoformat(),
              "window_end": we.isoformat()},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    allocation_id = created.json()["allocation_id"]

    wrong_outcome = await client.post(
        f"{CAP}/allocations/{allocation_id}/outcome",
        json={"outcome": "maybe"}, headers=headers,
    )
    assert wrong_outcome.status_code == 400
    assert "must be achieved, partial or missed" in wrong_outcome.json()["detail"]

    ok = await client.post(
        f"{CAP}/allocations/{allocation_id}/outcome",
        json={"outcome": "achieved", "note": "delivered on time"},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text

    twice = await client.post(
        f"{CAP}/allocations/{allocation_id}/outcome",
        json={"outcome": "missed"}, headers=headers,
    )
    assert twice.status_code == 400
    assert twice.json()["detail"] == "allocation is not active"


async def test_missing_capability_detail_and_isolated_what_if(
    client, db_session_factory,
):
    org = await register_org(client, email="4g4_miss@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    unknown = await client.get(
        f"{BRAIN}/execution/capacity/capabilities/never-demanded",
        headers=headers,
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "capability not found"

    p1 = await _project(db_session_factory, org_id, "Alone One")
    p2 = await _project(db_session_factory, org_id, "Alone Two")
    await _capability(db_session_factory, org_id, "security_eng")
    await _demand_org(client, headers, p1)
    await _drain(db_session_factory)

    isolated = await client.get(
        f"{BRAIN}/execution/capacity/what-if?from_project_id={p1}"
        f"&to_project_id={p2}&capability=security_eng&units=1",
        headers=headers,
    )
    assert isolated.status_code == 404
    assert "no shared demand window" in isolated.json()["detail"]