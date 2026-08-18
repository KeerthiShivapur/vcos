"""Slice 4G.5 — surfaces: the customer API walkthrough (signals, themes,
health, risk, commitments, outcomes, coverage, gaps, opportunities, trends,
knowledge linkage, customer command center) and the Universal Brain routing
of customer questions.

Everything is the canonical customer ledger: advisory, evidence-backed and
deterministic — never a dashboard.
"""

from datetime import date, timedelta

from sqlalchemy import select

from app.models.customer_intelligence import CustomerSignal
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
CUST = f"{BRAIN}/execution/customer"


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


async def _customer(client, headers, name="Nova Labs", tier="basic",
                    annual_value=None):
    body = {"company_name": name, "status": "customer", "segment": "mid_market",
            "tier": tier, "industry": "software", "country": "US",
            "timezone": "UTC", "source": "referral"}
    if annual_value is not None:
        body["annual_value"] = annual_value
    response = await client.post("/api/v1/customers", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _signal(client, headers, customer_id, signal_type="issue",
                  severity="medium", title="SSO login fails", source="support",
                  occurred_at=None):
    body = {
        "customer_id": customer_id, "signal_type": signal_type,
        "severity": severity, "summary": title, "source": source,
    }
    if occurred_at:
        body["occurred_at"] = occurred_at
    resp = await client.post(f"{CUST}/signals", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _ask(client, headers, question):
    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": question}, headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def test_surfaces_walkthrough(client, db_session_factory):
    org = await register_org(client, email="4g5_sur1@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    customer = await _customer(client, headers, name="Nova Labs", tier="gold",
                               annual_value=150000)
    other = await _customer(client, headers, name="Second Corp", tier="basic")

    # 3 demand-type signals on the same need (2 customers) + a resolved issue
    for i in range(3):
        await _signal(client, headers, customer, signal_type="request",
                      severity="medium",
                      title=f"SSO integration request {i}",
                      occurred_at=(date.today() - timedelta(days=i)).isoformat())
    await _signal(client, headers, other, signal_type="request",
                  severity="info", title="SSO docs request",
                  occurred_at=(date.today() - timedelta(days=2)).isoformat())
    await _signal(client, headers, customer, severity="high",
                  title="SSO outage blocks users")
    await _drain(db_session_factory)

    signals = (await client.get(f"{CUST}/signals", headers=headers)).json()
    assert signals["advisory_only"] is True
    assert signals["total"] == 5
    assert signals["by_type"]["request"] == 4
    assert all(s["need_key"] == "sso" for s in signals["signals"])

    filtered = (
        await client.get(
            f"{CUST}/signals", headers=headers,
            params={"severity": "high"},
        )
    ).json()
    assert filtered["total"] == 1
    assert filtered["signals"][0]["severity"] == "high"

    by_customer = (
        await client.get(
            f"{CUST}/signals", headers=headers,
            params={"customer_id": customer},
        )
    ).json()
    assert by_customer["total"] == 4

    themes = (await client.get(f"{CUST}/themes", headers=headers)).json()
    assert themes["advisory_only"] is True
    assert themes["themes"][0]["key"] == "sso"
    assert themes["themes"][0]["occurrences"] == 5
    assert themes["themes"][0]["customers"] == 2
    assert themes["themes"][0]["open"] == 5
    assert themes["themes"][0]["high_severity"] == 1
    assert len(themes["themes"][0]["evidence"]) >= 1
    assert themes["themes"][0]["evidence"][0]["customer"]

    healths = (await client.get(f"{CUST}/health", headers=headers)).json()
    assert healths["total"] == 2
    assert all(h["state"] in ("healthy", "concerned", "at_risk") for h in healths["health"])

    detail = (
        await client.get(f"{CUST}/health/{customer}", headers=headers)
    ).json()
    assert detail["customer"] == "Nova Labs"
    assert detail["tier"] == "gold"
    assert detail["score"] <= 100
    assert len(detail["history"]) >= 1
    assert detail["history"][0]["state"]

    risk = (await client.get(f"{CUST}/risk", headers=headers)).json()
    assert risk["advisory_only"] is True
    assert len(risk["at_risk_customers"]) >= 0
    assert risk["propagation_note"]

    commitments = (await client.get(f"{CUST}/commitments", headers=headers)).json()
    assert commitments["total"] == 0

    outcomes = (await client.get(f"{CUST}/outcomes", headers=headers)).json()
    assert outcomes["total"] == 0

    coverage = (await client.get(f"{CUST}/coverage", headers=headers)).json()
    assert coverage["advisory_only"] is True
    assert coverage["total_themes"] == 1
    assert coverage["themes"][0]["covered"] is False

    gaps = (await client.get(f"{CUST}/gaps", headers=headers)).json()
    assert gaps["advisory_only"] is True
    assert any(g["key"] == "sso" for g in gaps["gaps"])
    assert gaps["gaps"][0]["why"]

    opportunities = (
        await client.get(f"{CUST}/opportunities", headers=headers)
    ).json()
    assert opportunities["advisory_only"] is True
    assert any(o["key"] == "sso" for o in opportunities["opportunities"])
    assert opportunities["opportunities"][0]["decision_linkage"]["requires_decision"] is True

    trends = (await client.get(f"{CUST}/trends", headers=headers)).json()
    assert trends["advisory_only"] is True
    assert trends["themes"][0]["key"] == "sso"
    assert len(trends["themes"][0]["monthly"]) == 6
    assert sum(m["count"] for m in trends["themes"][0]["monthly"]) == 5

    knowledge = (await client.get(f"{CUST}/knowledge", headers=headers)).json()
    assert knowledge["advisory_only"] is True
    assert knowledge["knowledge_coverage_pct"] == 0.0
    assert knowledge["themes"][0]["knowledge_covered"] is False

    center = (
        await client.get(f"{CUST}/customers/{customer}", headers=headers)
    ).json()
    assert center["advisory_only"] is True
    assert center["customer"]["company_name"] == "Nova Labs"
    assert center["health"]["state"]
    assert len(center["signals"]) == 4
    assert all(s["status"] == "open" for s in center["signals"])
    assert len(center["themes"]) == 1


async def test_commitments_and_outcomes_surfaces(client, db_session_factory):
    org = await register_org(client, email="4g5_sur2@test.co")
    headers = org["headers"]
    customer = await _customer(client, headers)

    created = await client.post(
        f"{CUST}/commitments",
        json={"customer_id": customer, "summary": "SSO rollout",
              "expected_at": (date.today() + timedelta(days=20)).isoformat(),
              "capability": "sso", "owner_label": "Ada Owner"},
        headers=headers,
    )
    commitment_id = created.json()["commitment_id"]
    await _drain(db_session_factory)

    await client.post(
        f"{CUST}/outcomes",
        json={"customer_id": customer, "metric_kind": "login_success",
              "baseline": 70, "target": 95, "actual": 90, "unit": "pct"},
        headers=headers,
    )
    await _drain(db_session_factory)

    commitments = (await client.get(f"{CUST}/commitments", headers=headers)).json()
    assert commitments["total"] == 1
    assert commitments["commitments"][0]["status"] == "pending"
    assert commitments["commitments"][0]["owner_label"] == "Ada Owner"
    assert commitments["commitments"][0]["days_left"] >= 19

    pending_commitments = (
        await client.get(
            f"{CUST}/commitments", headers=headers, params={"status": "pending"},
        )
    ).json()
    assert pending_commitments["total"] == 1

    outcomes = (await client.get(f"{CUST}/outcomes", headers=headers)).json()
    assert outcomes["total"] == 1
    assert outcomes["outcomes"][0]["metric_kind"] == "login_success"
    assert outcomes["outcomes"][0]["improved"] is True

    delivered = await client.post(
        f"{CUST}/commitments/{commitment_id}/deliver",
        json={"delivered_at": date.today().isoformat()}, headers=headers,
    )
    assert delivered.status_code == 200, delivered.text
    await _drain(db_session_factory)

    delivered_commitments = (
        await client.get(
            f"{CUST}/commitments", headers=headers, params={"status": "delivered"},
        )
    ).json()
    assert delivered_commitments["total"] == 1
    assert delivered_commitments["commitments"][0]["status"] == "delivered"


async def test_brain_routes_customer_questions(client, db_session_factory):
    org = await register_org(client, email="4g5_sur3@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(client, headers, name="Nova Labs", tier="gold")

    for i in range(3):
        await _signal(client, headers, customer, severity="high",
                      title=f"SSO outage {i} blocks all users")
    await _drain(db_session_factory)

    risk = await _ask(client, headers, "which customers are at risk?")
    assert risk["intent"] == "customer_intelligence"
    assert risk["advisory_only"] is True
    assert risk["scope"] == "org"

    health = await _ask(client, headers, "how are our customers doing?")
    assert health["intent"] == "customer_intelligence"
    assert health["total"] == 1
    assert health["health"][0]["state"]

    needs = await _ask(client, headers, "what do our customers need?")
    assert needs["intent"] == "customer_intelligence"
    assert needs["themes"][0]["key"] == "sso"

    outcomes = await _ask(client, headers, "what are our customer outcomes?")
    assert outcomes["intent"] == "customer_intelligence"
    assert "outcomes" in outcomes
