"""Slice 4G.5 — Customer & Market Execution Intelligence engine.

Under test:

* signal.recorded -> one canonical CustomerSignal row; the affected theme
  aggregate is recomputed incrementally (occurrences, customer count, open
  count, high severity count, trend, bounded evidence) and the affected
  customer health is recomputed (state, score, why, positives, factors),
* exact-once replays: the same source_event_id converges to the same rows;
  one event only refreshes its OWN theme + customer neighborhood,
* signal.resolved stops weighing on health and re-feeds the health trail,
* commitments: created/updated/delivered land in the ledger and weigh on
  health (at risk / slipped / overdue reasons),
* outcome -> learning: a recorded outcome pours into 4E.7 learning with
  tags customer,4g5 and an improved verdict,
* risk: at-risk customers + commitment -> project -> strategic goal
  propagation,
* non-customer events are ignored.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.intelligence.customer_intelligence_engine import customer_intelligence_engine
from app.models.customer import Customer
from app.models.customer_intelligence import (
    CustomerCommitment,
    CustomerHealthHistory,
    CustomerHealthRow,
    CustomerOutcome,
    CustomerSignal,
    CustomerTheme,
)
from app.models.intelligence import LearningEvent
from app.models.notification import Event
from tests.conftest import register_org

CAP = "/api/v1/brain/execution/capacity"
CUST = "/api/v1/brain/execution/customer"


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


async def _publish(db_session_factory, org_id, actor_id, name, payload):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _customer(db_session_factory, org_id, name, tier="basic",
                    segment="mid_market", annual_value=None):
    async with db_session_factory() as db:
        customer = Customer(
            organization_id=org_id, company_name=name, status="customer",
            segment=segment, tier=tier, industry="software",
            annual_value=annual_value,
        )
        db.add(customer)
        await db.flush()
        cid = customer.id
        await db.commit()
    return cid


async def _signal(client, headers, customer_id, signal_type="issue",
                  severity="medium", title="SSO login fails", source="support",
                  need=None, occurred_at=None):
    body = {
        "customer_id": customer_id, "signal_type": signal_type,
        "severity": severity, "summary": title, "source": source,
        "occurred_at": occurred_at,
    }
    if need:
        body["need"] = need
    resp = await client.post(f"{CUST}/signals", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _counts(db_session_factory, org_id):
    async with db_session_factory() as db:
        return {
            "signals": len(list(
                (await db.execute(
                    select(CustomerSignal).where(
                        CustomerSignal.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "themes": len(list(
                (await db.execute(
                    select(CustomerTheme).where(
                        CustomerTheme.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "health": len(list(
                (await db.execute(
                    select(CustomerHealthRow).where(
                        CustomerHealthRow.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "history": len(list(
                (await db.execute(
                    select(CustomerHealthHistory).where(
                        CustomerHealthHistory.organization_id == org_id,
                    )
                )).scalars().all()
            )),
        }


# ---------------------------------------------------------------------------
# 1. Signal -> theme + health
# ---------------------------------------------------------------------------

async def test_signal_recorded_builds_theme_and_health(client, db_session_factory):
    org = await register_org(client, email="4g5_eng1@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    actor = org["user"]["id"]
    customer = await _customer(db_session_factory, org_id, "Nova Labs")

    await _signal(client, headers, customer, severity="high",
                  title="Customer cannot log in with SSO")
    await _signal(client, headers, customer, severity="low",
                  title="SSO sign-in fails for one office")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        signals = list(
            (await db.execute(
                select(CustomerSignal).where(
                    CustomerSignal.organization_id == org_id,
                )
            )).scalars().all()
        )
        assert len(signals) == 2
        assert all(s.need_key == "sso" for s in signals)

        theme = (
            await db.execute(
                select(CustomerTheme).where(
                    CustomerTheme.organization_id == org_id,
                    CustomerTheme.key == "sso",
                )
            )
        ).scalar_one()
        assert theme.occurrences == 2
        assert theme.customer_count == 1
        assert theme.open_count == 2
        assert theme.high_severity_count == 1
        assert theme.trend in ("worsening", "stable", "improving")
        assert len(theme.signal_ids_json or []) == 2
        assert customer in (theme.customer_ids_json or [])

        health = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == org_id,
                    CustomerHealthRow.customer_id == customer,
                )
            )
        ).scalar_one()
        assert health.state in ("healthy", "concerned", "at_risk")
        assert 0 <= health.score <= 100
        assert health.factors_json["signals"] == 2

        history = list(
            (await db.execute(
                select(CustomerHealthHistory).where(
                    CustomerHealthHistory.organization_id == org_id,
                ).order_by(CustomerHealthHistory.occurred_at)
            )).scalars().all()
        )
        assert len(history) == 2
        assert all(h.source_event_id for h in history)


async def test_health_drops_with_negative_signals_and_carries_the_why(
    client, db_session_factory,
):
    org = await register_org(client, email="4g5_eng2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(db_session_factory, org_id, "Beta Corp")

    for i in range(3):
        await _signal(client, headers, customer, severity="high",
                      title=f"SSO outage {i} blocks all users")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        health = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == org_id,
                    CustomerHealthRow.customer_id == customer,
                )
            )
        ).scalar_one()
        assert health.score <= 49
        assert health.state == "at_risk"
        assert any("critical" in r for r in (health.reasons_json or []))
        assert health.positives_json == []


async def test_exact_once_replay_converges(client, db_session_factory):
    org = await register_org(client, email="4g5_eng3@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(db_session_factory, org_id, "Gamma Inc")

    await _signal(client, headers, customer, severity="high", title="SSO down")

    async with db_session_factory() as db:
        event = (
            await db.execute(
                select(Event).where(
                    Event.organization_id == org_id,
                    Event.name == "customer.signal.recorded",
                )
            )
        ).scalars().one()
        event_id = event.id
        await customer_intelligence_engine.record_event(
            db, organization_id=org_id,
            event=SimpleNamespace(name=event.name, id=event.id),
            payload={
                "organization_id": org_id, "customer_id": customer,
                "signal_type": "issue", "severity": "high",
                "summary": "SSO down", "source": "support",
            },
        )
        await db.commit()

    counts = await _counts(db_session_factory, org_id)
    assert counts["signals"] == 1
    assert counts["themes"] == 1
    assert counts["health"] == 1
    assert counts["history"] == 1

    async with db_session_factory() as db:
        theme = (
            await db.execute(
                select(CustomerTheme).where(
                    CustomerTheme.organization_id == org_id,
                    CustomerTheme.key == "sso",
                )
            )
        ).scalar_one()
        assert theme.occurrences == 1
    assert event_id  # replay used the real event id


async def test_neighborhood_isolation_two_customers(client, db_session_factory):
    org = await register_org(client, email="4g5_eng4@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    ca = await _customer(db_session_factory, org_id, "Alpha Co")
    cb = await _customer(db_session_factory, org_id, "Omega Co")

    await _signal(client, headers, ca, severity="high", title="SSO login broken")
    await _signal(client, headers, cb, severity="info",
                  title="SSO onboarding doc request", signal_type="request")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        theme = (
            await db.execute(
                select(CustomerTheme).where(
                    CustomerTheme.organization_id == org_id,
                    CustomerTheme.key == "sso",
                )
            )
        ).scalar_one()
        assert theme.occurrences == 2
        assert theme.customer_count == 2
        assert theme.open_count == 2
        assert theme.high_severity_count == 1
        # evidence never merges customers: both ids are in the bounded list
        assert set(theme.customer_ids_json or []) == {ca, cb}


# ---------------------------------------------------------------------------
# 2. Resolution re-feeds health
# ---------------------------------------------------------------------------

async def test_signal_resolved_stops_weighing(client, db_session_factory):
    org = await register_org(client, email="4g5_eng5@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(db_session_factory, org_id, "Delta Ltd")

    await _signal(client, headers, customer, severity="high", title="SSO outage")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        signal = (
            await db.execute(
                select(CustomerSignal).where(
                    CustomerSignal.organization_id == org_id,
                )
            )
        ).scalars().one()
        signal_id = signal.id
        before = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == org_id,
                )
            )
        ).scalars().one()

    resolved = await client.post(
        f"{CUST}/signals/{signal_id}/resolve",
        json={"resolution": "fixed root cause"}, headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        signal = (
            await db.execute(
                select(CustomerSignal).where(
                    CustomerSignal.organization_id == org_id,
                    CustomerSignal.id == signal_id,
                )
            )
        ).scalar_one()
        assert signal.status == "resolved"

        health = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == org_id,
                    CustomerHealthRow.customer_id == customer,
                )
            )
        ).scalar_one()
        # the negative count stays (history is honest) but the unresolved
        # critical penalty disappears and the score recovers
        assert health.score > before.score
        assert "unresolved critical" not in " ".join(health.reasons_json or [])

        history = list(
            (await db.execute(
                select(CustomerHealthHistory).where(
                    CustomerHealthHistory.organization_id == org_id,
                )
            )).scalars().all()
        )
        assert len(history) >= 2


# ---------------------------------------------------------------------------
# 3. Commitments weigh on health
# ---------------------------------------------------------------------------

async def test_commitment_lifecycle_and_health_impact(client, db_session_factory):
    org = await register_org(client, email="4g5_eng6@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(db_session_factory, org_id, "Epsilon SA")

    created = await client.post(
        f"{CUST}/commitments",
        json={
            "customer_id": customer,
            "summary": "SSO rollout by end of month",
            "expected_at": (date.today() - timedelta(days=3)).isoformat(),
            "capability": "sso",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    commitment_id = created.json()["commitment_id"]
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        commitment = (
            await db.execute(
                select(CustomerCommitment).where(
                    CustomerCommitment.organization_id == org_id,
                    CustomerCommitment.id == commitment_id,
                )
            )
        ).scalar_one()
        assert commitment.status == "pending"
        health = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == org_id,
                    CustomerHealthRow.customer_id == customer,
                )
            )
        ).scalar_one()
        assert health.score <= 92
        assert any("overdue" in r for r in (health.reasons_json or []))

    changed = await client.post(
        f"{CUST}/commitments",
        json={
            "customer_id": customer,
            "summary": "SSO rollout by end of month",
            "expected_at": (date.today() - timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    await _drain(db_session_factory)

    delivered = await client.post(
        f"{CUST}/commitments/{commitment_id}/deliver",
        json={"delivered_at": date.today().isoformat()}, headers=headers,
    )
    assert delivered.status_code == 200, delivered.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        commitment = (
            await db.execute(
                select(CustomerCommitment).where(
                    CustomerCommitment.organization_id == org_id,
                    CustomerCommitment.id == commitment_id,
                )
            )
        ).scalar_one()
        assert commitment.status == "delivered"
        assert commitment.changed_at is not None

        health = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == org_id,
                    CustomerHealthRow.customer_id == customer,
                )
            )
        ).scalar_one()
        assert not any("overdue" in r for r in (health.reasons_json or []))
        assert not any("commitment" in r for r in (health.reasons_json or []))


# ---------------------------------------------------------------------------
# 4. Outcome -> learning
# ---------------------------------------------------------------------------

async def test_outcome_pours_into_learning(client, db_session_factory):
    org = await register_org(client, email="4g5_eng7@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(db_session_factory, org_id, "Zeta GmbH")

    recorded = await client.post(
        f"{CUST}/outcomes",
        json={
            "customer_id": customer, "metric_kind": "onboarding_time",
            "baseline": 30, "target": 15, "actual": 18,
            "unit": "days", "period_label": "Q3",
            "note": "SSO fix cut onboarding time",
        },
        headers=headers,
    )
    assert recorded.status_code == 200, recorded.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        outcome = (
            await db.execute(
                select(CustomerOutcome).where(
                    CustomerOutcome.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert outcome.metric_kind == "onboarding_time"
        assert outcome.actual == 18

        learnings = list(
            (
                await db.execute(
                    select(LearningEvent).where(
                        LearningEvent.organization_id == org_id,
                        LearningEvent.event_type == "customer.outcome",
                    )
                )
            ).scalars().all()
        )
        assert len(learnings) == 1
        assert "customer" in learnings[0].tags
        assert "4g5" in learnings[0].tags
        assert "toward target" in learnings[0].lesson

        health = (
            await db.execute(
                select(CustomerHealthRow).where(
                    CustomerHealthRow.organization_id == org_id,
                    CustomerHealthRow.customer_id == customer,
                )
            )
        ).scalar_one()
        assert any("outcome" in p for p in (health.positives_json or []))


# ---------------------------------------------------------------------------
# 5. Risk propagation
# ---------------------------------------------------------------------------

async def _goal_chain(client, headers, project_id):
    created = await client.post(
        "/api/v1/brain/execution/strategy/goals",
        json={"title": "Enterprise Revenue +25%", "kind": "revenue", "priority": 2,
              "metric_kind": "revenue", "metric_unit": "pct",
              "target_value": 25, "current_value": 5, "timeline_label": "FY2026"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    goal_id = created.json()["goal_id"]
    objective = await client.post(
        "/api/v1/brain/execution/strategy/objectives",
        json={"goal_id": goal_id, "title": "SSO rollout", "required_capabilities": ["sso"]},
        headers=headers,
    )
    assert objective.status_code in (200, 201), objective.text
    initiative = await client.post(
        "/api/v1/brain/execution/strategy/initiatives",
        json={"objective_id": objective.json()["objective_id"], "title": "SSO initiative"},
        headers=headers,
    )
    assert initiative.status_code in (200, 201), initiative.text
    linked = await client.post(
        f"/api/v1/brain/execution/strategy/initiatives/"
        f"{initiative.json()['initiative_id']}/link",
        json={"project_id": project_id}, headers=headers,
    )
    assert linked.status_code in (200, 201), linked.text


async def test_risk_propagation_from_commitment_to_goal(client, db_session_factory):
    org = await register_org(client, email="4g5_eng8@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(db_session_factory, org_id, "Theta Corp",
                               tier="gold", annual_value=120000)

    async with db_session_factory() as db:
        from app.models.project import Project

        project = Project(organization_id=org_id, name="SSO Rollout Project",
                          code="sso-r", status="active")
        db.add(project)
        await db.flush()
        project_id = project.id
        await db.commit()
    await _goal_chain(client, headers, project_id)

    for i in range(3):
        await _signal(client, headers, customer, severity="high",
                      title=f"SSO outage {i} blocks all users")

    created = await client.post(
        f"{CUST}/commitments",
        json={"customer_id": customer, "summary": "Enterprise SSO launch",
              "expected_at": (date.today() + timedelta(days=10)).isoformat(),
              "project_id": project_id, "capability": "sso"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    await _drain(db_session_factory)

    risk = (await client.get(f"{CUST}/risk", headers=headers)).json()
    assert risk["advisory_only"] is True
    assert any(r["customer_id"] == customer for r in risk["at_risk_customers"])

    commitment_rows = [
        c for c in risk["commitments_at_risk"]
        if c["commitment_id"] == created.json()["commitment_id"]
    ]
    assert len(commitment_rows) == 1
    entry = commitment_rows[0]
    assert entry["customer"] == "Theta Corp"
    assert entry["project"] == "SSO Rollout Project"
    assert any(g["goal"] == "Enterprise Revenue +25%" for g in entry["goals"])
    assert risk["propagation_note"]


# ---------------------------------------------------------------------------
# 6. Ignored events
# ---------------------------------------------------------------------------

async def test_non_customer_event_is_ignored(client, db_session_factory):
    org = await register_org(client, email="4g5_eng9@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    actor = org["user"]["id"]
    customer = await _customer(db_session_factory, org_id, "Iota SA")

    await _publish(db_session_factory, org_id, actor, "project.created",
                   {"organization_id": org_id, "name": "Noise"})

    counts = await _counts(db_session_factory, org_id)
    assert counts["signals"] == 0
    assert counts["themes"] == 0
    assert counts["health"] == 0