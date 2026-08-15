"""Slice 4F.1 — Universal People Intelligence Foundation.

The foundation every people surface (expertise 4F.2, experience 4F.3,
ownership 4F.4, collaboration 4F.5, capacity 4F.6) attaches to:

* canonical person profiles: identity, membership, roles, reporting — with
  full temporal window history (state moves forward, history is retained),
* identity resolution: one strong identifier maps to one person; conflicting
  links are refused — ambiguity is never silently merged,
* the living org chart + People Graph built from current open windows,
* event-driven updates (user.created / employee.offboarded / promoted /
  team.member.added) that are exact-once under replay,
* governance: scoped readers only see the people their visible scopes reach
  (downward-only — invisible subordinates are never revealed),
* tenant isolation across organizations,
* universal brain questions ("who works in X", "who reports to X",
  "who manages X", "org chart") routed to the governed people surfaces.
"""

import datetime

from sqlalchemy import select

from app.models.people_intelligence import (
    PeopleTimeline,
    PersonIdentity,
    PersonMembership,
    PersonRoleAssignment,
    ReportingRelationship,
)
from tests import _brain4d6_helpers as h
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
KNOWLEDGE = "/api/v1/brain/knowledge"


async def _drain(db_session_factory, limit=200, rounds=4):
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


async def _hire(client, headers, email, first, last, **extra):
    body = {"first_name": first, "last_name": last, "email": email, **extra}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _department(client, headers, name="Engineering", code=None):
    created = await client.post(
        "/api/v1/departments",
        json={"name": name, "code": code or f"dept-{name.lower()[:8]}"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _team(client, headers, name="Platform", code=None, department_id=None):
    created = await client.post(
        "/api/v1/teams",
        json={"name": name, "code": code or f"team-{name.lower()[:8]}",
              "department_id": department_id},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _team_scope(client, headers, team_id):
    created = await client.post(
        "/api/v1/governance/scopes",
        json={"name": f"People scope {team_id[:6]}", "scope_type": "team",
              "entity_id": team_id},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


# ---------------------------------------------------------------- foundation


async def test_people_directory_is_governed_and_bounded(client, db_session_factory):
    org = await register_org(client, email="4f1_dir@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    await _hire(client, headers, "4f1-a@test.co", "Aria", "Chen")
    await _hire(client, headers, "4f1-b@test.co", "Ben", "Okafor")
    await _hire(client, headers, "4f1-c@test.co", "Cara", "Lopez")
    await _drain(db_session_factory)

    directory = (await client.get(f"{BRAIN}/people", headers=headers)).json()
    assert directory["scope"] == "org_wide"
    assert directory["total_visible"] == 4, directory  # owner + 3 hires
    ids = {person["id"] for person in directory["people"]}
    assert len(ids) == 4

    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]

    profile = (await client.get(f"{BRAIN}/people/{me}", headers=headers)).json()
    assert profile["id"] == me
    assert profile["current_membership"]["employment_status"] == "active"
    assert profile["manager_id"] is None
    assert "identities" in profile


async def test_identity_resolution_never_merges_ambiguity(client):
    org = await register_org(client, email="4f1_idn@test.co")
    headers = org["headers"]
    first = await _hire(client, headers, "4f1-ida@test.co", "Dana", "Kelly")
    second = await _hire(client, headers, "4f1-idb@test.co", "Dev", "Rao")

    linked = await client.post(
        f"{BRAIN}/people/{first['id']}/identities",
        json={"source": "github", "source_key": "dana-dev", "verified": True},
        headers=headers,
    )
    assert linked.status_code == 200, linked.text

    resolved = (
        await client.post(
            f"{BRAIN}/people/identities/resolve",
            json={"source": "github", "source_key": "dana-dev"},
            headers=headers,
        )
    ).json()
    assert resolved == {"person_id": first["id"], "ambiguous": False, "note": "resolved"}

    unknown = (
        await client.post(
            f"{BRAIN}/people/identities/resolve",
            json={"source": "github", "source_key": "nobody-here"},
            headers=headers,
        )
    ).json()
    assert unknown["person_id"] is None
    assert unknown["ambiguous"] is False

    # the same strong key on another person is refused, never silently merged
    refused = await client.post(
        f"{BRAIN}/people/{second['id']}/identities",
        json={"source": "github", "source_key": "dana-dev", "verified": True},
        headers=headers,
    )
    assert refused.status_code == 409, refused.text

    # re-linking on the same person is an idempotent refresh
    again = await client.post(
        f"{BRAIN}/people/{first['id']}/identities",
        json={"source": "github", "source_key": "dana-dev", "verified": True},
        headers=headers,
    )
    assert again.status_code == 200, again.text

    # profile carries the identity links
    profile = (await client.get(f"{BRAIN}/people/{first['id']}", headers=headers)).json()
    assert any(i["source"] == "github" for i in profile["identities"])


async def test_membership_windows_are_temporal_and_mirror_status(client, db_session_factory):
    org = await register_org(client, email="4f1_mem@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f1-mem@test.co", "Eli", "Ng")

    await _drain(db_session_factory)

    base = datetime.datetime.now(datetime.timezone.utc)
    t0 = base + datetime.timedelta(minutes=2)
    t1 = t0 + datetime.timedelta(minutes=30)
    t2 = t1 + datetime.timedelta(minutes=30)

    first = await client.put(
        f"{BRAIN}/people/{person['id']}/membership",
        json={"employment_status": "suspended", "valid_from": t0.isoformat(),
              "note": "referred for review"},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    reopened = await client.put(
        f"{BRAIN}/people/{person['id']}/membership",
        json={"employment_status": "active", "valid_from": t1.isoformat(),
              "note": "back from leave"},
        headers=headers,
    )
    assert reopened.status_code == 200, reopened.text

    # employee status mirror: suspended -> inactive, active later
    employees = (await client.get("/api/v1/employees", headers=headers)).json()
    row = next(e for e in employees if e["id"] == person["id"])
    assert row["status"] == "active"

    history = (await client.get(f"{BRAIN}/people/{person['id']}/history", headers=headers)).json()
    statuses = [m["employment_status"] for m in history["history"]["memberships"]]
    assert statuses == ["active", "suspended", "active"], statuses
    assert any(m["valid_to"] is not None for m in history["history"]["memberships"])

    # temporal reconstruction: inside the suspension window we see suspended
    at = (await client.get(
        f"{BRAIN}/people/{person['id']}/at", params={"at": (t0 + datetime.timedelta(minutes=10)).isoformat()}, headers=headers
    )).json()
    assert at["membership"]["employment_status"] == "suspended"

    async with db_session_factory() as session:
        windows = (
            await session.execute(
                select(PersonMembership).where(
                    PersonMembership.organization_id == org["organization"]["id"],
                    PersonMembership.person_id == person["id"],
                )
            )
        ).scalars().all()
        assert len(windows) == 3, "windows are never deleted"
        await session.rollback()


async def test_role_windows_primary_change_and_removal(client):
    org = await register_org(client, email="4f1_role@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f1-role@test.co", "Faye", "Ruiz")

    primary = await client.post(
        f"{BRAIN}/people/{person['id']}/roles",
        json={"role_title": "Backend Engineer", "role_type": "functional",
              "is_primary": True},
        headers=headers,
    )
    assert primary.status_code == 200, primary.text
    first_id = primary.json()["id"]

    second = await client.post(
        f"{BRAIN}/people/{person['id']}/roles",
        json={"role_title": "Reliability Lead", "role_type": "project"},
        headers=headers,
    )
    second_id = second.json()["id"]

    changed = await client.post(
        f"{BRAIN}/people/roles/{second_id}/change",
        json={"role_title": "SRE Lead"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    continuation_id = changed.json()["id"]
    assert changed.json()["role_title"] == "SRE Lead"

    # designation mirrors the primary role; the function continues the window chain
    profile = (await client.get(f"{BRAIN}/people/{person['id']}", headers=headers)).json()
    assert profile["designation"] == "Backend Engineer"

    removed = await client.post(
        f"{BRAIN}/people/roles/{first_id}/remove", headers=headers
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["valid_to"] is not None

    history = (await client.get(f"{BRAIN}/people/{person['id']}/history", headers=headers)).json()
    roles = history["history"]["roles"]
    titles = [r["role_title"] for r in roles]
    assert titles == ["Backend Engineer", "Reliability Lead", "SRE Lead"], titles
    open_roles = [r for r in roles if r["valid_to"] is None]
    assert open_roles, "continuation window is open"
    assert open_roles[0]["role_title"] == "SRE Lead"

    kinds = {item["kind"] for item in history["history"]["timeline"]}
    assert {"role.assigned", "role.changed", "role.removed"} <= kinds, kinds

    # assignment to a person from another org is refused
    other = await register_org(client, email="4f1_role2@test.co")
    other_person = await _hire(client, other["headers"], "4f1-role2@test.co", "Gio", "Reed")
    outsider = await client.post(
        f"{BRAIN}/people/{other_person['id']}/roles",
        json={"role_title": "SRE Lead"},
        headers=headers,
    )
    assert outsider.status_code == 404, outsider.text


async def test_reporting_windows_drive_org_chart_and_line(client):
    org = await register_org(client, email="4f1_rep@test.co")
    headers = org["headers"]
    engineer = await _hire(client, headers, "4f1-rep1@test.co", "Hana", "Ito")
    lead = await _hire(client, headers, "4f1-rep2@test.co", "Ivan", "Marsh")
    manager = await _hire(client, headers, "4f1-rep3@test.co", "Jana", "Quist")
    founder = await _hire(client, headers, "4f1-rep4@test.co", "Ken", "Voss")

    report = await client.post(
        f"{BRAIN}/people/{engineer['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": lead["id"]},
        headers=headers,
    )
    assert report.status_code == 200, report.text
    await client.post(
        f"{BRAIN}/people/{lead['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": manager["id"]},
        headers=headers,
    )
    await client.post(
        f"{BRAIN}/people/{manager['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": founder["id"]},
        headers=headers,
    )

    # the open reports_to window mirrors Employee.manager_id (live org chart)
    profile = (await client.get(f"{BRAIN}/people/{engineer['id']}", headers=headers)).json()
    assert profile["manager_id"] == lead["id"]

    line = (
        await client.get(f"{BRAIN}/people/{engineer['id']}/reporting-line", headers=headers)
    ).json()
    assert [m["name"] for m in line["manager_chain"]] == ["Ivan Marsh", "Jana Quist", "Ken Voss"]

    chart = (await client.get(f"{BRAIN}/org/chart", headers=headers)).json()
    assert chart["scope"] == "org_wide"

    def find(root, person_id):
        if root["id"] == person_id:
            return root
        for child in root.get("children", []):
            found = find(child, person_id)
            if found:
                return found
        return None

    founder_root = next(r for r in chart["roots"] if r["id"] == founder["id"])
    manager_node = find(founder_root, manager["id"])
    assert manager_node is not None
    lead_node = find(manager_node, lead["id"])
    assert lead_node is not None
    assert any(c["id"] == engineer["id"] for c in lead_node["children"])


async def test_reporting_history_reconstructed_as_of(client):
    org = await register_org(client, email="4f1_hist@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f1-hista@test.co", "Lena", "Ward")
    old_manager = await _hire(client, headers, "4f1-histb@test.co", "Milo", "Xan")
    new_manager = await _hire(client, headers, "4f1-histc@test.co", "Nina", "Yee")

    t0 = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)
    t1 = t0 + datetime.timedelta(days=5)

    await client.post(
        f"{BRAIN}/people/{person['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": old_manager["id"],
              "valid_from": t0.isoformat()},
        headers=headers,
    )
    await client.post(
        f"{BRAIN}/people/{person['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": new_manager["id"],
              "valid_from": t1.isoformat()},
        headers=headers,
    )

    past = (
        await client.get(
            f"{BRAIN}/people/{person['id']}/at",
            params={"at": (t0 + datetime.timedelta(days=2)).isoformat()},
            headers=headers,
        )
    ).json()
    assert past["reporting_at"][-1]["manager_person_id"] == old_manager["id"]
    assert past["manager_name"] == "Milo Xan"

    now_world = (
        await client.get(
            f"{BRAIN}/people/{person['id']}/at",
            params={"at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
            headers=headers,
        )
    ).json()
    assert now_world["manager_name"] == "Nina Yee"

    history = (await client.get(f"{BRAIN}/people/{person['id']}/history", headers=headers)).json()
    windows = history["history"]["reporting"]
    assert len(windows) == 2, "past reporting windows survive"


async def test_related_people_are_deterministic_and_explained(client):
    org = await register_org(client, email="4f1_rel@test.co")
    headers = org["headers"]
    dept = await _department(client, headers, "Product")
    team = await _team(client, headers, "Search", department_id=dept["id"])
    p1 = await _hire(client, headers, "4f1-rel1@test.co", "Owen", "Pei",
                     department_id=dept["id"], team_id=team["id"])
    p2 = await _hire(client, headers, "4f1-rel2@test.co", "Pia", "Qin",
                     department_id=dept["id"], team_id=team["id"])
    p3 = await _hire(client, headers, "4f1-rel3@test.co", "Quinn", "Ross",
                     department_id=dept["id"])
    mentor = await _hire(client, headers, "4f1-rel4@test.co", "Rhea", "Sato")
    await client.post(
        f"{BRAIN}/people/{p1['id']}/reporting",
        json={"relationship_type": "mentor", "manager_person_id": mentor["id"]},
        headers=headers,
    )

    related = (await client.get(f"{BRAIN}/people/{p1['id']}/related", headers=headers)).json()
    relations = {r["person_id"]: r["relation"] for r in related["relations"]}
    assert relations[p2["id"]] == "same_team", relations
    assert relations[p3["id"]] == "same_department", relations
    assert relations[mentor["id"]] == "mentor", relations
    assert related["scope"] == "org_wide"


async def test_people_graph_nodes_and_edges(client):
    org = await register_org(client, email="4f1_graph@test.co")
    headers = org["headers"]
    dept = await _department(client, headers, "Operations")
    team = await _team(client, headers, "SRE", department_id=dept["id"])
    p1 = await _hire(client, headers, "4f1-g1@test.co", "Sana", "Tan",
                     department_id=dept["id"], team_id=team["id"])
    p2 = await _hire(client, headers, "4f1-g2@test.co", "Tariq", "Umar")
    await client.post(
        f"{BRAIN}/people/{p2['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": p1["id"]},
        headers=headers,
    )
    await client.post(
        f"{BRAIN}/people/{p1['id']}/roles",
        json={"role_title": "Principal Engineer", "role_type": "functional",
              "is_primary": True},
        headers=headers,
    )

    graph = (await client.get(f"{BRAIN}/org/graph", headers=headers)).json()
    node_types = {node["type"] for node in graph["nodes"]}
    assert {"person", "team", "department", "role"} <= node_types, node_types
    edges = [edge for edge in graph["edges"] if edge["relation"] == "reports_to"]
    assert any(edge["source"] == p2["id"] and edge["target"] == p1["id"] for edge in edges)
    member_edges = [e for e in graph["edges"] if e["relation"] == "member_of"]
    assert any(e["source"] == p1["id"] and e["target"] == team["id"] for e in member_edges)


async def test_units_summary_and_members(client):
    org = await register_org(client, email="4f1_unit@test.co")
    headers = org["headers"]
    dept = await _department(client, headers, "Data")
    team = await _team(client, headers, "Analytics", department_id=dept["id"])
    await _hire(client, headers, "4f1-u1@test.co", "Uma", "Vale",
                department_id=dept["id"], team_id=team["id"])
    await _hire(client, headers, "4f1-u2@test.co", "Vera", "Walsh",
                department_id=dept["id"])

    summary = (await client.get(f"{BRAIN}/org/units/summary", headers=headers)).json()
    data_dept = next(d for d in summary["departments"] if d["id"] == dept["id"])
    assert data_dept["members_count"] == 2, data_dept
    analytics = next(t for t in summary["teams"] if t["id"] == team["id"])
    assert analytics["members_count"] == 1, analytics

    members = (
        await client.get(
            f"{BRAIN}/org/units", params={"unit_kind": "team", "unit_id": team["id"]},
            headers=headers,
        )
    ).json()
    assert members["members_count"] == 1
    assert members["members"][0]["email"] == "4f1-u1@test.co"

    bad_kind = await client.get(
        f"{BRAIN}/org/units", params={"unit_kind": "planet", "unit_id": "x"},
        headers=headers,
    )
    assert bad_kind.status_code == 422, bad_kind.text
    missing = await client.get(
        f"{BRAIN}/org/units", params={"unit_kind": "team", "unit_id": "nope"},
        headers=headers,
    )
    assert missing.status_code == 404, missing.text


async def test_people_search_surfaces(client):
    org = await register_org(client, email="4f1_search@test.co")
    headers = org["headers"]
    dept = await _department(client, headers, "Growth")
    team = await _team(client, headers, "Acquisition", department_id=dept["id"])
    await _hire(client, headers, "4f1-s1@test.co", "Wren", "Zhao",
                department_id=dept["id"], team_id=team["id"], designation="Growth Engineer")

    found = (await client.get(f"{BRAIN}/people/search", params={"q": "wren"}, headers=headers)).json()
    assert len(found["people"]) == 1
    assert found["people"][0]["first_name"] == "Wren"

    team_hit = (await client.get(f"{BRAIN}/people/search", params={"q": "acquisition"}, headers=headers)).json()
    assert len(team_hit["teams"]) == 1
    dept_hit = (await client.get(f"{BRAIN}/people/search", params={"q": "growth"}, headers=headers)).json()
    assert len(dept_hit["departments"]) >= 1


# ---------------------------------------------------------------- governance


async def test_scoped_reader_sees_only_their_team(client):
    org = await register_org(client, email="4f1_scope@test.co")
    headers = org["headers"]
    dept = await _department(client, headers, "Platform")
    visible_team = await _team(client, headers, "Core", department_id=dept["id"])
    hidden_team = await _team(client, headers, "Edge", department_id=dept["id"])
    visible_guy = await _hire(client, headers, "4f1-sc1@test.co", "Xin", "Yan",
                              department_id=dept["id"], team_id=visible_team["id"])
    await _hire(client, headers, "4f1-sc2@test.co", "Yara", "Zane",
                department_id=dept["id"], team_id=hidden_team["id"])
    lead = await _hire(client, headers, "4f1-sc3@test.co", "Zayn", "Adeyemi",
                       department_id=dept["id"])

    scope = await _team_scope(client, headers, visible_team["id"])
    scoped = await h.invite_scoped_reader(client, headers, scope["id"], "4f1-reader@test.co")

    directory = (await client.get(f"{BRAIN}/people", headers=scoped)).json()
    assert directory["scope"] == "scoped"
    ids = {p["id"] for p in directory["people"]}
    assert visible_guy["id"] in ids

    all_employees = (await client.get("/api/v1/employees", headers=headers)).json()
    hidden_person = next(e for e in all_employees if e["team_id"] == hidden_team["id"])
    assert hidden_person["id"] not in ids, "invisible team member is not revealed"
    assert lead["id"] not in ids, "unanchored colleague is not revealed"

    # the unit surface is bounded by the same visibility
    hidden_unit = (
        await client.get(
            f"{BRAIN}/org/units", params={"unit_kind": "team", "unit_id": hidden_team["id"]},
            headers=scoped,
        )
    ).json()
    assert hidden_unit["members_count"] == 0, hidden_unit


async def test_scoped_reader_org_chart_never_reveals_subordinates(client):
    org = await register_org(client, email="4f1_chartscope@test.co")
    headers = org["headers"]
    team = await _team(client, headers, "Alpha")
    boss = await _hire(client, headers, "4f1-cs1@test.co", "Abel", "Birch")
    visible_peer = await _hire(client, headers, "4f1-cs2@test.co", "Bella", "Crane",
                               team_id=team["id"])
    hidden_report = await _hire(client, headers, "4f1-cs3@test.co", "Cid", "Drake")
    await client.post(
        f"{BRAIN}/people/{visible_peer['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": boss["id"]},
        headers=headers,
    )
    await client.post(
        f"{BRAIN}/people/{hidden_report['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": visible_peer["id"]},
        headers=headers,
    )

    scope = await _team_scope(client, headers, team["id"])
    scoped = await h.invite_scoped_reader(client, headers, scope["id"], "4f1-csreader@test.co")

    chart = (await client.get(f"{BRAIN}/org/chart", headers=scoped)).json()
    flat: list[str] = []

    def walk(roots):
        for root in roots:
            flat.append(root["id"])
            walk(root.get("children", []))

    walk(chart["roots"])
    assert visible_peer["id"] in flat
    assert hidden_report["id"] not in flat, "invisible subordinate below the peer is concealed"
    # the manager chain above the visible peer is allowed (downward-only keeps
    # everyone ABOVE visible, and never below)
    assert boss["id"] in flat


async def test_scoped_reader_people_question_is_bounded(client):
    org = await register_org(client, email="4f1_qscope@test.co")
    headers = org["headers"]
    team = await _team(client, headers, "Nebula")
    await _hire(client, headers, "4f1-qs1@test.co", "Dara", "Eze", team_id=team["id"])
    await _hire(client, headers, "4f1-qs2@test.co", "Elio", "Field")
    scope = await _team_scope(client, headers, team["id"])
    scoped = await h.invite_scoped_reader(client, headers, scope["id"], "4f1-qsreader@test.co")

    answer = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "who works in the Nebula team?"},
            headers=scoped,
        )
    ).json()
    assert answer["intent"] == "people", answer
    assert answer["kind"] == "unit_members"
    names = {p["name"] for p in answer["answers"]}
    assert names and all("Elio Field" not in name for name in names), answer


# ---------------------------------------------------------------- brain questions


async def test_brain_question_who_works_in(client):
    org = await register_org(client, email="4f1_q1@test.co")
    headers = org["headers"]
    team = await _team(client, headers, "Ignition")
    await _hire(client, headers, "4f1-q1a@test.co", "Faiz", "Ghosh", team_id=team["id"])
    await _hire(client, headers, "4f1-q1b@test.co", "Gul", "Hart", team_id=team["id"])

    answer = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "who works in the Ignition team?"},
            headers=headers,
        )
    ).json()
    assert answer["intent"] == "people", answer
    assert answer["kind"] == "unit_members"
    names = {p["name"] for p in answer["answers"]}
    assert "Faiz Ghosh" in names and "Gul Hart" in names, names
    assert "Ignition" in answer["answer"]


async def test_brain_question_who_reports_to_or_manages(client):
    org = await register_org(client, email="4f1_q2@test.co")
    headers = org["headers"]
    lead = await _hire(client, headers, "4f1-q2a@test.co", "Hugo", "Iyer")
    report_a = await _hire(client, headers, "4f1-q2b@test.co", "Ines", "Jump")
    report_b = await _hire(client, headers, "4f1-q2c@test.co", "Joon", "Kim")
    await client.post(
        f"{BRAIN}/people/{report_a['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": lead["id"]},
        headers=headers,
    )
    await client.post(
        f"{BRAIN}/people/{report_b['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": lead["id"]},
        headers=headers,
    )

    direct = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "who reports to Hugo Iyer?"},
            headers=headers,
        )
    ).json()
    assert direct["intent"] == "people", direct
    assert direct["kind"] == "direct_reports"
    names = {r["name"] for r in direct["answers"]}
    assert names == {"Ines Jump", "Joon Kim"}, direct

    line = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "who manages Ines Jump?"},
            headers=headers,
        )
    ).json()
    assert line["kind"] == "reporting_line"
    assert "Hugo Iyer" in line["answer"]


async def test_brain_question_org_chart(client):
    org = await register_org(client, email="4f1_q3@test.co")
    headers = org["headers"]
    root = await _hire(client, headers, "4f1-q3a@test.co", "Kai", "Lane")
    child = await _hire(client, headers, "4f1-q3b@test.co", "Lia", "Moon")
    await client.post(
        f"{BRAIN}/people/{child['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": root["id"]},
        headers=headers,
    )
    answer = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "show me the org chart"},
            headers=headers,
        )
    ).json()
    assert answer["intent"] == "people", answer
    assert answer["kind"] == "org_chart"
    assert answer["total"] >= 2


# ---------------------------------------------------------------- events


async def test_person_events_are_exact_once_under_replay(client, db_session_factory):
    org = await register_org(client, email="4f1_evt@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f1-evt@test.co", "Mara", "North")
    await _drain(db_session_factory)

    from app.events.event_bus import event_bus
    from app.events import handlers as people_handlers

    async with db_session_factory() as db:
        event = await event_bus.publish(
            db,
            name="employee.promoted",
            organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"employee_id": person["id"], "new_designation": "Senior Engineer"},
            enqueue=False, flush=False,
        )
        await db.commit()

        # apply once (handler-level replay safety)
        payload = {"employee_id": person["id"], "new_designation": "Senior Engineer"}
        for _ in range(2):
            await people_handlers.handle_people_employee_promoted(db, event, payload)
        await db.commit()
        timeline_rows = (
            await db.execute(
                select(PeopleTimeline).where(
                    PeopleTimeline.organization_id == org_id,
                    PeopleTimeline.person_id == person["id"],
                    PeopleTimeline.event_id == event.id,
                )
            )
        ).scalars().all()
        assert len(timeline_rows) == 1, "the same durable event journals once"
        role_windows = (
            await db.execute(
                select(PersonRoleAssignment).where(
                    PersonRoleAssignment.organization_id == org_id,
                    PersonRoleAssignment.person_id == person["id"],
                )
            )
        ).scalars().all()
        assert len(role_windows) == 1, "the promotion opened exactly one role window"
        await db.rollback()

    profile = (await client.get(f"{BRAIN}/people/{person['id']}", headers=headers)).json()
    assert profile["designation"] == "Senior Engineer"


async def test_offboarding_event_closes_membership_once(client, db_session_factory):
    org = await register_org(client, email="4f1_offbrd@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f1-off@test.co", "Noor", "Owens")
    await _drain(db_session_factory)

    from app.events.event_bus import event_bus
    from app.events import handlers as people_handlers

    async with db_session_factory() as db:
        event = await event_bus.publish(
            db,
            name="employee.offboarded",
            organization_id=org_id,
            actor_id=person["id"],
            payload={"employee_id": person["id"], "reason": "resigned"},
            enqueue=False, flush=False,
        )
        await db.commit()
        payload = {"employee_id": person["id"], "reason": "resigned"}
        for _ in range(2):
            await people_handlers.handle_people_employee_offboarded(db, event, payload)
        await db.commit()
        windows = (
            await db.execute(
                select(PersonMembership).where(
                    PersonMembership.organization_id == org_id,
                    PersonMembership.person_id == person["id"],
                )
            )
        ).scalars().all()
        statuses = [w.employment_status for w in windows]
        assert statuses == ["active", "departed"], statuses
        assert windows[0].valid_to is not None
        await db.rollback()

    history = (await client.get(f"{BRAIN}/people/{person['id']}/history", headers=headers)).json()
    assert any(m["employment_status"] == "departed" for m in history["history"]["memberships"])


async def test_team_member_events_journal_the_timeline(client, db_session_factory):
    org = await register_org(client, email="4f1_team@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    team = await _team(client, headers, "Comet")
    person = await _hire(client, headers, "4f1-team@test.co", "Omar", "Perez")
    joined = await client.post(
        f"/api/v1/teams/{team['id']}/members",
        json={"employee_id": person["id"], "role": "member"},
        headers=headers,
    )
    assert joined.status_code == 201, joined.text
    await _drain(db_session_factory)

    # today's hire on a team already emitted a team event; ensure replay of
    # the event bus produces one journal row per durable event
    async with db_session_factory() as db:
        from app.models.notification import Event as EventRow

        rows = (
            await db.execute(
                select(PeopleTimeline).where(
                    PeopleTimeline.organization_id == org_id,
                    PeopleTimeline.person_id == person["id"],
                )
            )
        ).scalars().all()
        kinds = {row.kind for row in rows}
        assert "team.joined" in kinds, kinds
        assert "person.created" in kinds, kinds

        processed = (
            await db.execute(
                select(EventRow.processed_at).where(
                    EventRow.organization_id == org_id,
                    EventRow.name.in_(("user.created", "employee.created",
                                       "employee.joined", "team.member.added")),
                    EventRow.processed_at.is_(None),
                )
            )
        ).scalars().all()
        assert not processed, "all people events drained"
        await db.rollback()


# ---------------------------------------------------------------- tenants


async def test_people_are_tenant_isolated(client):
    org_a = await register_org(client, email="4f1_tena@test.co")
    org_b = await register_org(client, email="4f1_tenb@test.co")
    person_a = await _hire(client, org_a["headers"], "4f1-ta@test.co", "Prakash", "Qureshi")
    await _hire(client, org_b["headers"], "4f1-tb@test.co", "Qasim", "Reyes")

    a_directory = (await client.get(f"{BRAIN}/people", headers=org_a["headers"])).json()
    a_ids = {p["id"] for p in a_directory["people"]}
    assert person_a["id"] in a_ids
    assert all("4f1-tb@test.co" != p["email"] for p in a_directory["people"]), "no cross-tenant leak"

    # identity keys are tenant-scoped: the same key resolves per organization
    await client.post(
        f"{BRAIN}/people/{person_a['id']}/identities",
        json={"source": "slack", "source_key": "qasim-dev"},
        headers=org_a["headers"],
    )
    resolved_a = (
        await client.post(
            f"{BRAIN}/people/identities/resolve",
            json={"source": "slack", "source_key": "qasim-dev"},
            headers=org_a["headers"],
        )
    ).json()
    resolved_b = (
        await client.post(
            f"{BRAIN}/people/identities/resolve",
            json={"source": "slack", "source_key": "qasim-dev"},
            headers=org_b["headers"],
        )
    ).json()
    assert resolved_a["person_id"] == person_a["id"]
    assert resolved_b["person_id"] is None, "tenant B never sees tenant A identity keys"

    # role writes from tenant A against tenant B's person are refused
    outsider = await client.post(
        f"{BRAIN}/people/{person_a['id']}/roles",
        json={"role_title": "Guest"},
        headers=org_b["headers"],
    )
    assert outsider.status_code == 404, outsider.text


async def test_write_surfaces_require_manage_permission(client):
    org = await register_org(client, email="4f1_perm@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f1-perm@test.co", "Riva", "Silva")
    team = await _team(client, headers, "Raider")
    scope = await _team_scope(client, headers, team["id"])
    reader = await h.invite_scoped_reader(client, headers, scope["id"], "4f1-permreader@test.co")

    # unauthenticated writes are refused
    anonymous = await client.post(
        f"{BRAIN}/people/{person['id']}/roles",
        json={"role_title": "Backend Engineer", "role_type": "functional",
              "is_primary": True},
    )
    assert anonymous.status_code == 401, anonymous.text

    # a scoped reader holds brain:read (delegated) but NOT employees:manage
    forbidden = await client.post(
        f"{BRAIN}/people/{person['id']}/roles",
        json={"role_title": "Backend Engineer", "role_type": "functional",
              "is_primary": True},
        headers=reader,
    )
    assert forbidden.status_code == 403, forbidden.text

    # the owner (admin) can mutate
    allowed = await client.post(
        f"{BRAIN}/people/{person['id']}/roles",
        json={"role_title": "Backend Engineer", "role_type": "functional",
              "is_primary": True},
        headers=headers,
    )
    assert allowed.status_code == 200, allowed.text


async def test_invalid_inputs_are_rejected(client):
    org = await register_org(client, email="4f1_inv@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f1-inv@test.co", "Sal", "Tate")

    bad_status = await client.put(
        f"{BRAIN}/people/{person['id']}/membership",
        json={"employment_status": "warped"},
        headers=headers,
    )
    assert bad_status.status_code == 400, bad_status.text

    bad_role_type = await client.post(
        f"{BRAIN}/people/{person['id']}/roles",
        json={"role_title": "X", "role_type": "teleporter"},
        headers=headers,
    )
    assert bad_role_type.status_code == 400, bad_role_type.text

    empty_title = await client.post(
        f"{BRAIN}/people/{person['id']}/roles",
        json={"role_title": "   ", "role_type": "functional"},
        headers=headers,
    )
    assert empty_title.status_code == 400, empty_title.text

    self_report = await client.post(
        f"{BRAIN}/people/{person['id']}/reporting",
        json={"relationship_type": "reports_to", "manager_person_id": person["id"]},
        headers=headers,
    )
    assert self_report.status_code == 400, self_report.text

    unknown_person = await client.get(f"{BRAIN}/people/missing-person", headers=headers)
    assert unknown_person.status_code == 404, unknown_person.text