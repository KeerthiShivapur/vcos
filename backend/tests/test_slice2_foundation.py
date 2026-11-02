"""Vertical Slice 2 — People & Organization foundation tests.

Covers organization structure (1-8), manager safety (9-14), the event
catalog (15-21), notifications (22-24), permissions (25-27), audit (28),
and tenancy isolation (29-30).
"""

import uuid

import pytest

from tests.conftest import register_org


# --------------------------------------------------------------------------- helpers


async def _invite(client, headers, email, role="employee", full_name="Invitee"):
    return await client.post(
        "/api/v1/users/invite",
        json={"email": email, "role": role, "full_name": full_name},
        headers=headers,
    )


async def _accept(client, token, email, full_name="Invitee", password="InviteePass123!"):
    return await client.post(
        "/api/v1/auth/register/invite",
        json={"token": token, "email": email, "full_name": full_name, "password": password},
    )


async def _accept_invite(client, headers, email, full_name="Invitee"):
    """Invite an email and accept it; returns the accepted user payload."""
    resp = await _invite(client, headers, email, full_name=full_name)
    assert resp.status_code == 201, resp.text
    accepted = await _accept(client, resp.json()["token"], email, full_name)
    assert accepted.status_code == 201, accepted.text
    return accepted.json()


async def _create_department(client, headers, name, code):
    return await client.post(
        "/api/v1/departments", json={"name": name, "code": code}, headers=headers
    )


async def _create_employee(client, headers, first_name, email, designation=None):
    payload = {"first_name": first_name, "email": email}
    if designation:
        payload["designation"] = designation
    return await client.post("/api/v1/employees", json=payload, headers=headers)


async def _set_manager(client, headers, employee_id, manager_id):
    return await client.patch(
        f"/api/v1/employees/{employee_id}",
        json={"manager_id": manager_id},
        headers=headers,
    )


async def _process_pending(db_session_factory, limit=50):
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        for _ in range(200):
            processed = await event_bus.process_pending(session, limit=limit)
            await session.commit()
            if not processed:
                return
        raise AssertionError("event dispatch did not quiesce")


async def _notifications(client, headers):
    return (await client.get("/api/v1/notifications", headers=headers)).json()["items"]


async def _event_payloads(db_session_factory, org_id, name):
    import json

    from sqlalchemy import select

    from app.models.notification import Event

    async with db_session_factory() as session:
        rows = (
            await session.execute(
                select(Event).where(
                    Event.organization_id == org_id,
                    Event.name == name,
                )
            )
        ).scalars().all()
        return [json.loads(r.payload_json or "{}") for r in rows]


# --------------------------------------------------------------------------- organization structure


@pytest.mark.asyncio
async def test_create_department(client):
    org = await register_org(client, email="s2dept1@test.co")
    r = await _create_department(client, org["headers"], "Engineering", "eng")
    assert r.status_code == 201, r.text
    dept = r.json()
    assert dept["name"] == "Engineering"
    assert dept["code"] == "eng"

    listing = (await client.get("/api/v1/departments", headers=org["headers"])).json()
    assert any(d["id"] == dept["id"] for d in listing)


@pytest.mark.asyncio
async def test_duplicate_department_code_rejected(client):
    org = await register_org(client, email="s2dept2@test.co")
    await _create_department(client, org["headers"], "Engineering", "eng")
    r = await _create_department(client, org["headers"], "Engineering Ops", "eng")
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_update_department_head(client):
    org = await register_org(client, email="s2dept3@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    r = await client.patch(
        f"/api/v1/departments/{dept['id']}",
        json={"head_id": ada["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["head_id"] == ada["id"]

    detail = (await client.get(f"/api/v1/departments/{dept['id']}", headers=org["headers"])).json()
    assert detail["head_id"] == ada["id"]


@pytest.mark.asyncio
async def test_create_team_with_lead(client):
    org = await register_org(client, email="s2team1@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    r = await client.post(
        "/api/v1/teams",
        json={"name": "Backend", "code": "be", "department_id": dept["id"], "lead_id": ada["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    team = r.json()
    assert team["lead_id"] == ada["id"]
    assert team["department_id"] == dept["id"]


@pytest.mark.asyncio
async def test_duplicate_team_code_rejected(client):
    org = await register_org(client, email="s2team2@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    await client.post(
        "/api/v1/teams",
        json={"name": "Backend", "code": "be", "department_id": dept["id"], "lead_id": ada["id"]},
        headers=org["headers"],
    )
    r = await client.post(
        "/api/v1/teams",
        json={"name": "Backend Ops", "code": "be", "department_id": dept["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_team_member_add_and_remove(client):
    org = await register_org(client, email="s2team3@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    team = (
        await client.post(
            "/api/v1/teams",
            json={"name": "Backend", "code": "be", "department_id": dept["id"], "lead_id": ada["id"]},
            headers=org["headers"],
        )
    ).json()
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co", "Engineer")).json()

    r = await client.post(
        f"/api/v1/teams/{team['id']}/members",
        json={"employee_id": bob["id"], "role": "Member"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text

    detail = (await client.get(f"/api/v1/teams/{team['id']}", headers=org["headers"])).json()
    assert any(m["employee_id"] == bob["id"] for m in detail["members"])

    r = await client.delete(f"/api/v1/teams/{team['id']}/members/{bob['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text

    detail = (await client.get(f"/api/v1/teams/{team['id']}", headers=org["headers"])).json()
    assert all(m["employee_id"] != bob["id"] for m in detail["members"])


@pytest.mark.asyncio
async def test_org_chart_reflects_manager_hierarchy(client):
    org = await register_org(client, email="s2chart@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (await _set_manager(client, org["headers"], bob["id"], ada["id"])).status_code == 200

    chart = (await client.get("/api/v1/organization/chart", headers=org["headers"])).json()
    assert chart["total"] >= 2
    ids = {n["id"] for n in chart["roots"]}
    assert ada["id"] in ids
    root = next(n for n in chart["roots"] if n["id"] == ada["id"])
    assert any(c["id"] == bob["id"] for c in root["children"])


@pytest.mark.asyncio
async def test_org_graph_reports_to_edge(client, db_session_factory):
    org = await register_org(client, email="s2graph@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (await _set_manager(client, org["headers"], bob["id"], ada["id"])).status_code == 200
    await _process_pending(db_session_factory)

    graph = (await client.get("/api/v1/organization/graph", headers=org["headers"])).json()
    manages = [e for e in graph["edges"] if e["relation"] == "manages"]
    assert any(e["source"] == ada["id"] and e["target"] == bob["id"] for e in manages)

    from sqlalchemy import select

    from app.models.intelligence import OrgGraphEdge

    async with db_session_factory() as session:
        edges = (
            await session.execute(
                select(OrgGraphEdge).where(
                    OrgGraphEdge.organization_id == org["organization"]["id"],
                    OrgGraphEdge.relation == "reports_to",
                    OrgGraphEdge.source_id == bob["id"],
                    OrgGraphEdge.target_id == ada["id"],
                    OrgGraphEdge.active.is_(True),
                )
            )
        ).scalars().all()
    assert edges, "manager.changed handler must persist the reports_to graph edge"


# --------------------------------------------------------------------------- manager safety


@pytest.mark.asyncio
async def test_self_manager_rejected(client):
    org = await register_org(client, email="s2cyc1@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    r = await _set_manager(client, org["headers"], ada["id"], ada["id"])
    assert r.status_code == 400, r.text
    assert "own manager" in r.json()["detail"]


@pytest.mark.asyncio
async def test_direct_cycle_rejected(client):
    org = await register_org(client, email="s2cyc2@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (await _set_manager(client, org["headers"], bob["id"], ada["id"])).status_code == 200

    r = await _set_manager(client, org["headers"], ada["id"], bob["id"])
    assert r.status_code == 400, r.text
    assert "cycle" in r.json()["detail"]


@pytest.mark.asyncio
async def test_transitive_cycle_rejected(client):
    org = await register_org(client, email="s2cyc3@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    carol = (await _create_employee(client, org["headers"], "Carol", f"carol-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (await _set_manager(client, org["headers"], bob["id"], ada["id"])).status_code == 200
    assert (await _set_manager(client, org["headers"], carol["id"], bob["id"])).status_code == 200

    r = await _set_manager(client, org["headers"], ada["id"], carol["id"])
    assert r.status_code == 400, r.text
    assert "cycle" in r.json()["detail"]


@pytest.mark.asyncio
async def test_rejected_cycle_leaves_manager_unchanged(client):
    org = await register_org(client, email="s2cyc4@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (await _set_manager(client, org["headers"], bob["id"], ada["id"])).status_code == 200

    r = await _set_manager(client, org["headers"], ada["id"], bob["id"])
    assert r.status_code == 400, r.text

    refreshed = (await client.get(f"/api/v1/employees/{ada['id']}", headers=org["headers"])).json()
    assert refreshed["manager_id"] is None
    refreshed = (await client.get(f"/api/v1/employees/{bob['id']}", headers=org["headers"])).json()
    assert refreshed["manager_id"] == ada["id"]


@pytest.mark.asyncio
async def test_valid_manager_assignment_succeeds(client):
    org = await register_org(client, email="s2cyc5@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    r = await _set_manager(client, org["headers"], bob["id"], ada["id"])
    assert r.status_code == 200, r.text
    assert r.json()["manager_id"] == ada["id"]

    reports = (await client.get(f"/api/v1/employees/{ada['id']}/reports", headers=org["headers"])).json()
    assert any(e["id"] == bob["id"] for e in reports)


@pytest.mark.asyncio
async def test_clearing_manager_allowed(client):
    org = await register_org(client, email="s2cyc6@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (await _set_manager(client, org["headers"], bob["id"], ada["id"])).status_code == 200

    r = await client.patch(
        f"/api/v1/employees/{bob['id']}", json={"manager_id": None}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["manager_id"] is None


# --------------------------------------------------------------------------- event catalog


@pytest.mark.asyncio
async def test_event_department_created_emitted(client, db_session_factory):
    org = await register_org(client, email="s2evt1@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    events = (await client.get("/api/v1/events", headers=org["headers"])).json()["items"]
    assert any(e["name"] == "department.created" for e in events)
    payloads = await _event_payloads(db_session_factory, org["organization"]["id"], "department.created")
    assert payloads and payloads[0]["department_id"] == dept["id"]


@pytest.mark.asyncio
async def test_event_department_updated_emitted(client):
    org = await register_org(client, email="s2evt2@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    r = await client.patch(
        f"/api/v1/departments/{dept['id']}", json={"name": "Engineering Plus"}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    events = (await client.get("/api/v1/events", headers=org["headers"])).json()["items"]
    assert any(e["name"] == "department.updated" for e in events)


@pytest.mark.asyncio
async def test_event_team_created_emitted(client, db_session_factory):
    org = await register_org(client, email="s2evt3@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    team = (
        await client.post(
            "/api/v1/teams",
            json={"name": "Backend", "code": "be", "department_id": dept["id"]},
            headers=org["headers"],
        )
    ).json()
    events = (await client.get("/api/v1/events", headers=org["headers"])).json()["items"]
    assert any(e["name"] == "team.created" for e in events)
    payloads = await _event_payloads(db_session_factory, org["organization"]["id"], "team.created")
    assert payloads and payloads[0]["team_id"] == team["id"]


@pytest.mark.asyncio
async def test_event_team_member_added_emitted(client, db_session_factory):
    org = await register_org(client, email="s2evt4@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    team = (
        await client.post(
            "/api/v1/teams",
            json={"name": "Backend", "code": "be", "department_id": dept["id"]},
            headers=org["headers"],
        )
    ).json()
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (
        await client.post(
            f"/api/v1/teams/{team['id']}/members",
            json={"employee_id": bob["id"]},
            headers=org["headers"],
        )
    ).status_code == 201
    events = (await client.get("/api/v1/events", headers=org["headers"])).json()["items"]
    assert any(e["name"] == "team.member.added" for e in events)
    payloads = await _event_payloads(db_session_factory, org["organization"]["id"], "team.member.added")
    assert payloads and payloads[0]["employee_id"] == bob["id"]


@pytest.mark.asyncio
async def test_event_team_member_removed_emitted(client):
    org = await register_org(client, email="s2evt5@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    team = (
        await client.post(
            "/api/v1/teams",
            json={"name": "Backend", "code": "be", "department_id": dept["id"]},
            headers=org["headers"],
        )
    ).json()
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    await client.post(
        f"/api/v1/teams/{team['id']}/members", json={"employee_id": bob["id"]}, headers=org["headers"]
    )
    assert (
        await client.delete(f"/api/v1/teams/{team['id']}/members/{bob['id']}", headers=org["headers"])
    ).status_code == 200
    events = (await client.get("/api/v1/events", headers=org["headers"])).json()["items"]
    assert any(e["name"] == "team.member.removed" for e in events)


@pytest.mark.asyncio
async def test_event_manager_changed_emitted_with_payload(client, db_session_factory):
    org = await register_org(client, email="s2evt6@test.co")
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (await _set_manager(client, org["headers"], bob["id"], ada["id"])).status_code == 200

    events = (await client.get("/api/v1/events", headers=org["headers"])).json()["items"]
    assert any(e["name"] == "manager.changed" for e in events)
    payloads = await _event_payloads(db_session_factory, org["organization"]["id"], "manager.changed")
    assert payloads
    payload = payloads[0]
    assert payload["employee_id"] == bob["id"]
    assert payload["from"] is None
    assert payload["to"] == ada["id"]


@pytest.mark.asyncio
async def test_event_employee_transferred_emitted(client, db_session_factory):
    org = await register_org(client, email="s2evt7@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    r = await client.patch(
        f"/api/v1/employees/{bob['id']}",
        json={"department_id": dept["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 200, r.text

    events = (await client.get("/api/v1/events", headers=org["headers"])).json()["items"]
    assert any(e["name"] == "employee.transferred" for e in events)
    payloads = await _event_payloads(db_session_factory, org["organization"]["id"], "employee.transferred")
    assert payloads and payloads[0]["to_department"] == dept["id"]


# --------------------------------------------------------------------------- notifications


@pytest.mark.asyncio
async def test_manager_change_notifies_employee_and_manager(client, db_session_factory):
    org = await register_org(client, email="s2notif1@test.co")
    alice = await _accept_invite(client, org["headers"], "alice@s2n1.test.co", "Alice")
    bob = await _accept_invite(client, org["headers"], "bob@s2n1.test.co", "Bob")
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    alice_emp = next(e for e in employees if e["email"] == "alice@s2n1.test.co")
    bob_emp = next(e for e in employees if e["email"] == "bob@s2n1.test.co")

    r = await _set_manager(client, org["headers"], bob_emp["id"], alice_emp["id"])
    assert r.status_code == 200, r.text
    await _process_pending(db_session_factory)

    bob_titles = {n["title"] for n in await _notifications(client, bob_headers)}
    assert "Manager changed" in bob_titles
    alice_titles = {n["title"] for n in await _notifications(client, alice_headers)}
    assert "New direct report" in alice_titles


@pytest.mark.asyncio
async def test_team_member_added_notifies_member_and_lead(client, db_session_factory):
    org = await register_org(client, email="s2notif2@test.co")
    alice = await _accept_invite(client, org["headers"], "alice@s2n2.test.co", "Alice")
    bob = await _accept_invite(client, org["headers"], "bob@s2n2.test.co", "Bob")
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    alice_emp = next(e for e in employees if e["email"] == "alice@s2n2.test.co")
    bob_emp = next(e for e in employees if e["email"] == "bob@s2n2.test.co")

    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    team = (
        await client.post(
            "/api/v1/teams",
            json={"name": "Backend", "code": "be", "department_id": dept["id"], "lead_id": alice_emp["id"]},
            headers=org["headers"],
        )
    ).json()
    assert (
        await client.post(
            f"/api/v1/teams/{team['id']}/members",
            json={"employee_id": bob_emp["id"]},
            headers=org["headers"],
        )
    ).status_code == 201
    await _process_pending(db_session_factory)

    bob_titles = {n["title"] for n in await _notifications(client, bob_headers)}
    assert any(t.startswith("Added to team") for t in bob_titles)
    alice_titles = {n["title"] for n in await _notifications(client, alice_headers)}
    assert "Team member added" in alice_titles


@pytest.mark.asyncio
async def test_team_member_removed_notifies_member_and_lead(client, db_session_factory):
    org = await register_org(client, email="s2notif3@test.co")
    alice = await _accept_invite(client, org["headers"], "alice@s2n3.test.co", "Alice")
    bob = await _accept_invite(client, org["headers"], "bob@s2n3.test.co", "Bob")
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    alice_emp = next(e for e in employees if e["email"] == "alice@s2n3.test.co")
    bob_emp = next(e for e in employees if e["email"] == "bob@s2n3.test.co")

    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    team = (
        await client.post(
            "/api/v1/teams",
            json={"name": "Backend", "code": "be", "department_id": dept["id"], "lead_id": alice_emp["id"]},
            headers=org["headers"],
        )
    ).json()
    await client.post(
        f"/api/v1/teams/{team['id']}/members", json={"employee_id": bob_emp["id"]}, headers=org["headers"]
    )
    assert (
        await client.delete(f"/api/v1/teams/{team['id']}/members/{bob_emp['id']}", headers=org["headers"])
    ).status_code == 200
    await _process_pending(db_session_factory)

    bob_titles = {n["title"] for n in await _notifications(client, bob_headers)}
    assert any(t.startswith("Removed from team") for t in bob_titles)
    alice_titles = {n["title"] for n in await _notifications(client, alice_headers)}
    assert "Team member removed" in alice_titles


# --------------------------------------------------------------------------- permissions


@pytest.mark.asyncio
async def test_employee_role_cannot_create_department(client):
    org = await register_org(client, email="s2perm1@test.co")
    invitee = await _accept_invite(client, org["headers"], "worker@s2p1.test.co", "Worker")
    worker_headers = {"Authorization": f"Bearer {invitee['access_token']}"}

    r = await _create_department(client, worker_headers, "Rogue Dept", "rog")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_employee_role_cannot_update_employee(client):
    org = await register_org(client, email="s2perm2@test.co")
    invitee = await _accept_invite(client, org["headers"], "worker@s2p2.test.co", "Worker")
    worker_headers = {"Authorization": f"Bearer {invitee['access_token']}"}

    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    r = await _set_manager(client, worker_headers, ada["id"], ada["id"])
    assert r.status_code in (403, 400), r.text


@pytest.mark.asyncio
async def test_employee_role_can_read_directory(client):
    org = await register_org(client, email="s2perm3@test.co")
    invitee = await _accept_invite(client, org["headers"], "worker@s2p3.test.co", "Worker")
    worker_headers = {"Authorization": f"Bearer {invitee['access_token']}"}

    r = await client.get("/api/v1/employees", headers=worker_headers)
    assert r.status_code == 200, r.text
    assert r.json()  # the directory is visible to employees


# --------------------------------------------------------------------------- audit


@pytest.mark.asyncio
async def test_organization_changes_are_audited(client):
    org = await register_org(client, email="s2audit@test.co")
    dept = (await _create_department(client, org["headers"], "Engineering", "eng")).json()
    employees = (await client.get("/api/v1/employees", headers=org["headers"])).json()
    ada = next(e for e in employees if e["email"] == org["user"]["email"])
    bob = (await _create_employee(client, org["headers"], "Bob", f"bob-{uuid.uuid4().hex[:6]}@s2.test.co")).json()
    assert (await _set_manager(client, org["headers"], bob["id"], ada["id"])).status_code == 200
    assert (
        await client.patch(
            f"/api/v1/employees/{bob['id']}", json={"department_id": dept["id"]}, headers=org["headers"]
        )
    ).status_code == 200

    audit = (await client.get("/api/v1/audit", headers=org["headers"])).json()["items"]
    actions = {e["action"] for e in audit}
    assert "department.created" in actions
    assert "employee.created" in actions
    assert "manager.changed" in actions
    assert "employee.transferred" in actions
    manager_entries = [e for e in audit if e["action"] == "manager.changed"]
    assert manager_entries[0]["resource_id"] == bob["id"]
    assert manager_entries[0]["details"]["to"] == ada["id"]


# --------------------------------------------------------------------------- tenancy


@pytest.mark.asyncio
async def test_cross_organization_department_404(client):
    org_a = await register_org(client, email="s2ten1a@test.co")
    org_b = await register_org(client, email="s2ten1b@test.co", name="Other Corp", slug="other-tenantx")
    dept = (await _create_department(client, org_a["headers"], "Engineering", "eng")).json()

    r = await client.get(f"/api/v1/departments/{dept['id']}", headers=org_b["headers"])
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_cross_organization_employee_404(client):
    org_a = await register_org(client, email="s2ten2a@test.co")
    org_b = await register_org(client, email="s2ten2b@test.co", name="Other Corp", slug="other-tenant2x")
    employees = (await client.get("/api/v1/employees", headers=org_a["headers"])).json()
    ada = next(e for e in employees if e["email"] == org_a["user"]["email"])

    r = await client.get(f"/api/v1/employees/{ada['id']}", headers=org_b["headers"])
    assert r.status_code == 404, r.text
