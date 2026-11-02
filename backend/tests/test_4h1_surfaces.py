"""Slice 4H.1 — API surfaces for Universal Company / Organizational
Intelligence: schemas, bounds, defaults unchanged for the 4G.7 surfaces."""

from tests.conftest import register_org

COMPANY = "/api/v1/brain/execution/company"


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


async def test_state_defaults_stay_org_level(client, db_session_factory):
    org = await register_org(client, email="4h1_surf@test.co")
    headers = org["headers"]

    resp = await client.get(f"{COMPANY}/state", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # the 4G.7 surface is byte-compatible: same keys, org-wide default.
    assert body["advisory_only"] is True
    assert body["organization_id"] == org["organization"]["id"]
    assert "dimensions" in body
    assert "attention" in body
    assert "generated_at" in body


async def test_state_temporal_series_with_scope(client, db_session_factory):
    org = await register_org(client, email="4h1_series@test.co")
    headers = org["headers"]

    resp = await client.get(
        f"{COMPANY}/state?scope_type=team&scope_id=some-team",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scope_type"] == "team"
    assert body["series"] == []
    assert body["latest"] is None
    # no trail yet -> the live multi-level snapshot is attached.
    assert body["live_snapshot"]["scope_type"] == "team"
    assert body["live_snapshot"]["company_score"] == 80

    resp = await client.get(
        f"{COMPANY}/state?from=2026-01-01&to=2030-01-01&limit=5",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json()["series"], list)

    resp = await client.get(
        f"{COMPANY}/state?limit=99", headers=headers,
    )
    assert resp.status_code == 422, resp.text  # bound enforced


async def test_narrative_surface(client, db_session_factory):
    org = await register_org(client, email="4h1_nsurf@test.co")
    headers = org["headers"]

    resp = await client.get(f"{COMPANY}/narrative", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["window"] == "insufficient_history"
    assert "story" in body and "steps" in body

    resp = await client.get(f"{COMPANY}/narrative?window=3", headers=headers)
    assert resp.status_code == 200, resp.text


async def test_causal_chain_surface(client, db_session_factory):
    org = await register_org(client, email="4h1_chain_surf@test.co")
    headers = org["headers"]

    resp = await client.get(
        f"{COMPANY}/causal-chain?subject_type=project&subject_id=nope",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject"] == {"type": "project", "id": "nope"}
    assert "hops" in body and "depth" in body
    assert body["advisory_only"] is True

    resp = await client.get(
        f"{COMPANY}/causal-chain", headers=headers,
    )
    assert resp.status_code == 422, resp.text


async def test_what_happens_if_surface(client, db_session_factory):
    org = await register_org(client, email="4h1_whisurf@test.co")
    headers = org["headers"]

    resp = await client.post(
        f"{COMPANY}/what-happens-if",
        json={"scenario_type": "delay", "payload": {"project_id": "nope", "days": 5}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scenario_type"] == "delay"
    assert body["not_a_prediction"] is True
    assert "company_consequences" in body
    assert body["company_consequences"] == []

    resp = await client.post(
        f"{COMPANY}/what-happens-if",
        json={"scenario_type": "reallocate",
              "from_project_id": "a", "to_project_id": "b",
              "capability": "x", "units": 1},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert "company_consequences" in resp.json()


async def test_decision_schema_with_prediction(client, db_session_factory):
    org = await register_org(client, email="4h1_decide_surf@test.co")
    headers = org["headers"]

    resp = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "predict hire",
              "predicted_outcome": {"expected_outcome": "successful"},
              "prediction_confidence": 0.6},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # byte-compatible keys + the prediction marker.
    assert body["decision_recorded"] is True
    assert body["decision_id"]
    assert body["prediction_recorded"] is True
    assert body["source_event_id"]

    resp = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "bad prediction",
              "prediction_confidence": 1.5},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text

    resp = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "negative prediction",
              "prediction_confidence": -0.2},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


async def test_outcome_surface_returns_compare_and_lesson(client, db_session_factory):
    org = await register_org(client, email="4h1_out_surf@test.co")
    headers = org["headers"]

    approved = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "delay_project", "title": "predict delay",
              "predicted_outcome": {"expected_outcome": "partial"},
              "prediction_confidence": 0.55},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    decision_id = approved.json()["decision_id"]
    await _drain(db_session_factory)
    await client.post(
        f"{COMPANY}/decisions/{decision_id}/execute",
        json={}, headers=headers,
    )
    await _drain(db_session_factory)

    resp = await client.post(
        f"{COMPANY}/decisions/{decision_id}/outcome",
        json={"outcome_kind": "partial", "effectiveness": 0.5,
              "lesson": "partial outcomes still protect the customer"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["actual_outcome_compare"]["predicted"] == "partial"
    assert body["actual_outcome_compare"]["observed"] == "partial"
    assert body["actual_outcome_compare"]["aligned"] is True
    assert body["lesson_memory"]["fact_kind"] == "lesson"

    resp = await client.post(
        f"{COMPANY}/decisions/{decision_id}/outcome",
        json={"outcome_kind": "bogus"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
