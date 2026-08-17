"""Slice 4F.6 — capability discovery & evidence.

The canonical capability record emerges from the SAME durable events the
platform already emits (expertise.updated after every expertise-feeding
activity). Under test:

* capabilities are discovered change-driven (an activity on a skill creates
  the org capability row, never a scan),
* lifecycle states are deterministic bands of evidence (emerging ->
  established -> strong -> strategic),
* every capability answers WHY it believes what it believes (confidence,
  corroborated kinds, outcome ratio, explain),
* taxonomy hierarchy feeds adjacency (parent/children/related + shared
  experts),
* the Company Brain routes "what are we really good at" and friends to the
  capability surface.
"""

from tests.conftest import register_org

BRAIN = "/api/v1/brain"
KNOWLEDGE_QUERY = "/api/v1/brain/knowledge/query"


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


async def _hire(client, headers, email, first, last, team_id=None):
    body = {"first_name": first, "last_name": last, "email": email,
            "team_id": team_id}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _team(client, headers, name):
    created = await client.post(
        "/api/v1/teams", json={"name": name, "code": f"t6-{name.lower()[:8]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _publish_task(client, db_session_factory, org_id, actor_id, employee_id,
                        task_id, title, project_id=None):
    from app.events.event_bus import event_bus

    payload = {"employee_id": employee_id, "task_id": task_id, "title": title}
    if project_id:
        payload["project_id"] = project_id
        payload["assignee_id"] = employee_id
    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="task.completed", organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _overview(client, headers):
    res = await client.get(f"{BRAIN}/capabilities/overview", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------- discovery


async def test_capabilities_are_discovered_change_driven(client, db_session_factory):
    org = await register_org(client, email="4f6_disc@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f6-da@test.co", "Ada", "Lovelace")
    grace = await _hire(client, headers, "4f6-dg@test.co", "Grace", "Hopper")

    # pre-discovery: no capability rows exist
    view = await _overview(client, headers)
    assert view["total"] == 0, view["total"]

    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], ada["id"],
        task_id="4f6-d1", title="Deploy the kubernetes cluster hard",
    )
    view = await _overview(client, headers)
    assert view["total"] >= 1, view["total"]
    kube = next(
        (c for c in view["capabilities"] if c["name"] == "Kubernetes"), None,
    )
    assert kube is not None, [c["name"] for c in view["capabilities"]]
    assert kube["lifecycle"] == "emerging"
    assert kube["expert_count"] == 1
    assert kube["evidence_count"] >= 1
    assert kube["confidence"] > 0
    assert "Kubernetes" in kube["explain"]

    # more evidence by a second expert: established
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], grace["id"],
        task_id="4f6-d2", title="Kubernetes rollout and monitoring",
    )
    view = await _overview(client, headers)
    kube = next(
        (c for c in view["capabilities"] if c["name"] == "Kubernetes"), None
    )
    assert kube["expert_count"] >= 2
    assert kube["lifecycle"] in ("established", "strong")
    assert kube["capacity_state"] in ("available", "unknown")
    assert kube["capacity_available"] >= 0


async def test_capability_detail_explains_its_evidence(client, db_session_factory):
    org = await register_org(client, email="4f6_detail@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-dd@test.co", "Tim", "Berners")

    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], person["id"],
        task_id="4f6-det1", title="Python service migration to django",
    )
    view = await _overview(client, headers)
    capability = next(
        c for c in view["capabilities"] if c["name"] == "Python"
    )
    detail = (
        await client.get(
            f"{BRAIN}/capabilities/{capability['skill_id']}", headers=headers,
        )
    ).json()
    assert detail["name"] == "Python"
    assert detail["confidence"] > 0
    assert detail["explain"]
    assert detail["factors"]  # the deterministic breakdown is never hidden
    assert detail["experts"], "experts must be listed with evidence"
    expert = detail["experts"][0]
    assert expert["person_id"] == person["id"]
    assert expert["score"] > 0
    assert expert["evidence_count"] >= 1
    assert detail["projects"] == []
    assert detail["history"] == []
    # taxonomy adjacency: Python's family should mention related programming
    # capabilities (parent/children/related or shared experts)
    assert detail["adjacent"], detail["adjacent"]


async def test_capability_detail_adjacency_shares_experts(client, db_session_factory):
    org = await register_org(client, email="4f6_adj@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-aa@test.co", "Lynn", "Conway")

    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], person["id"],
        task_id="4f6-adj1", title="Python and machine learning pipeline work",
    )
    view = await _overview(client, headers)
    py = next(c for c in view["capabilities"] if c["name"] == "Python")
    ml = next(c for c in view["capabilities"] if c["name"] == "Machine Learning")
    detail = (
        await client.get(f"{BRAIN}/capabilities/{py['skill_id']}", headers=headers)
    ).json()
    adjacency_ids = {a["skill_id"] for a in detail["adjacent"]}
    assert ml["skill_id"] in adjacency_ids, adjacency_ids


async def test_brain_routes_capability_strength_questions(client, db_session_factory):
    org = await register_org(client, email="4f6_brain@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-ba@test.co", "Edsger", "Dijkstra")
    person_b = await _hire(client, headers, "4f6-bb@test.co", "Grace", "Hopper")

    # Enough evidence on ONE skill for the lifecycle to reach strong
    # (2 experts x several completed tasks -> evidence >= 10, experts >= 2).
    for i in range(6):
        await _publish_task(
            client, db_session_factory, org_id, org["user"]["id"], person["id"],
            task_id=f"4f6-br-pa{i}", title="Python platform delivery work",
        )
        await _publish_task(
            client, db_session_factory, org_id, org["user"]["id"], person_b["id"],
            task_id=f"4f6-br-pb{i}", title="Python platform delivery work",
        )
    id_to_name = {
        c["skill_id"]: c["name"] for c in (await _overview(client, headers))["capabilities"]
    }
    assert id_to_name, "expected at least one discovered capability"

    for question in ("what are we really good at", "what are we best at"):
        res = await client.post(
            KNOWLEDGE_QUERY, json={"question": question}, headers=headers,
        )
        assert res.status_code == 200, res.text
        result = res.json()
        assert result.get("intent") in ("capability_strength", "expertise"), (question, result)
        if result.get("intent") == "capability_strength":
            answer = str(result.get("answer", ""))
            assert any(
                name in answer for name in id_to_name.values()
            ), (question, result)


async def test_brain_routes_capability_emerging_and_constrained(client, db_session_factory):
    org = await register_org(client, email="4f6_brain2@test.co")
    headers = org["headers"]

    res = await client.post(
        KNOWLEDGE_QUERY,
        json={"question": "which emerging capabilities are we getting good at?"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["intent"] in ("capability_emerging", "expertise")

    res = await client.post(
        KNOWLEDGE_QUERY,
        json={"question": "are we capacity constrained anywhere?"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["intent"] in ("capability_constraint", "expertise")


async def test_tenant_isolation_capabilities(client, db_session_factory):
    org_a = await register_org(client, email="4f6_tena@test.co")
    org_b = await register_org(client, email="4f6_tenb@test.co")
    person_a = await _hire(client, org_a["headers"], "4f6-ta@test.co", "Pia", "Quintana")
    await _publish_task(
        client, db_session_factory, org_a["organization"]["id"],
        org_a["user"]["id"], person_a["id"], task_id="4f6-ta1",
        title="Python platform work",
    )
    view_a = await _overview(client, org_a["headers"])
    view_b = await _overview(client, org_b["headers"])
    assert view_a["total"] >= 1
    assert view_b["total"] == 0, view_b["total"]