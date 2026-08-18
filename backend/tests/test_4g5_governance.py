"""Slice 4G.5 — governance: the event catalog, route validation, RBAC scope
gating, event-bus wiring and multi-tenant isolation.

Every write is governed (auth + scope), every signal/commitment/outcome
event is documented, and a scoped reader never sees the org-wide customer
view.
"""

from sqlalchemy import select

from app.models.customer_intelligence import CustomerCommitment, CustomerSignal
from app.models.notification import Event
from tests._brain4d6_helpers import invite_scoped_reader
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
CUST = f"{BRAIN}/execution/customer"

G4_5_EVENTS = {
    "customer.signal.recorded",
    "customer.signal.resolved",
    "customer.commitment.created",
    "customer.commitment.updated",
    "customer.commitment.delivered",
    "customer.outcome.recorded",
}


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


async def _customer(client, headers, name="Nova Labs", tier="basic"):
    response = await client.post(
        "/api/v1/customers",
        json={"company_name": name, "status": "customer", "segment": "mid_market",
              "tier": tier, "industry": "software", "country": "US",
              "timezone": "UTC", "source": "referral"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def test_catalog_documents_all_4g5_events():
    from app.events.event_models import EVENT_CATALOG

    assert G4_5_EVENTS <= set(EVENT_CATALOG)


async def test_signal_route_validates_enum_fields(client, db_session_factory):
    org = await register_org(client, email="4g5_gov2@test.co")
    headers = org["headers"]
    customer = await _customer(client, headers)

    bad_type = await client.post(
        f"{CUST}/signals",
        json={"customer_id": customer, "signal_type": "rumor", "severity": "high",
              "summary": "x", "source": "support"},
        headers=headers,
    )
    assert bad_type.status_code == 400
    assert "signal_type" in bad_type.json()["detail"]

    bad_severity = await client.post(
        f"{CUST}/signals",
        json={"customer_id": customer, "signal_type": "issue", "severity": "extreme",
              "summary": "x", "source": "support"},
        headers=headers,
    )
    assert bad_severity.status_code == 400

    bad_source = await client.post(
        f"{CUST}/signals",
        json={"customer_id": customer, "signal_type": "issue", "severity": "high",
              "summary": "x", "source": "rumor"},
        headers=headers,
    )
    assert bad_source.status_code == 400

    missing_customer = await client.post(
        f"{CUST}/signals",
        json={"signal_type": "issue", "severity": "high", "summary": "x",
              "source": "support"},
        headers=headers,
    )
    assert missing_customer.status_code == 400

    unknown_customer = await client.post(
        f"{CUST}/signals",
        json={"customer_id": "does-not-exist", "signal_type": "issue",
              "severity": "high", "summary": "x", "source": "support"},
        headers=headers,
    )
    assert unknown_customer.status_code == 404


async def test_writes_require_authentication(client):
    response = await client.post(
        f"{CUST}/signals",
        json={"customer_id": "x", "signal_type": "issue", "severity": "high",
              "summary": "x", "source": "support"},
    )
    assert response.status_code in (401, 403)


async def test_scoped_reader_sees_no_customer_view(client, db_session_factory):
    org = await register_org(client, email="4g5_gov4@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(client, headers)

    recorded = await client.post(
        f"{CUST}/signals",
        json={"customer_id": customer, "signal_type": "issue", "severity": "high",
              "summary": "SSO down", "source": "support"},
        headers=headers,
    )
    assert recorded.status_code == 200, recorded.text
    await _drain(db_session_factory)

    scope = await client.post(
        "/api/v1/governance/scopes",
        json={"name": "4g5 scope", "scope_type": "organization", "entity_id": org_id},
        headers=headers,
    )
    assert scope.status_code in (200, 201), scope.text
    scoped_headers = await invite_scoped_reader(
        client, headers, scope.json()["id"], "reader4g5@test.co"
    )

    health = await client.get(f"{CUST}/health", headers=scoped_headers)
    assert health.status_code == 404
    signals = await client.get(f"{CUST}/signals", headers=scoped_headers)
    assert signals.status_code == 404
    risk = await client.get(f"{CUST}/risk", headers=scoped_headers)
    assert risk.status_code == 404

    write = await client.post(
        f"{CUST}/signals",
        json={"customer_id": customer, "signal_type": "issue", "severity": "high",
              "summary": "x", "source": "support"},
        headers=scoped_headers,
    )
    assert write.status_code in (403, 404)


async def test_double_resolution_rejected(client, db_session_factory):
    org = await register_org(client, email="4g5_gov5@test.co")
    headers = org["headers"]
    customer = await _customer(client, headers)

    recorded = await client.post(
        f"{CUST}/signals",
        json={"customer_id": customer, "signal_type": "issue", "severity": "high",
              "summary": "SSO down", "source": "support"},
        headers=headers,
    )
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        signal_id = (
            await db.execute(
                select(CustomerSignal).where(
                    CustomerSignal.organization_id == org["organization"]["id"],
                )
            )
        ).scalars().one().id

    first = await client.post(
        f"{CUST}/signals/{signal_id}/resolve",
        json={"resolution": "fixed"}, headers=headers,
    )
    assert first.status_code == 200, first.text
    await _drain(db_session_factory)

    second = await client.post(
        f"{CUST}/signals/{signal_id}/resolve",
        json={"resolution": "again"}, headers=headers,
    )
    assert second.status_code == 400
    assert "already" in second.json()["detail"]


async def test_double_delivery_rejected(client, db_session_factory):
    org = await register_org(client, email="4g5_gov6@test.co")
    headers = org["headers"]
    customer = await _customer(client, headers)

    created = await client.post(
        f"{CUST}/commitments",
        json={"customer_id": customer, "summary": "SSO rollout",
              "expected_at": "2026-12-31", "capability": "sso"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    commitment_id = created.json()["commitment_id"]
    await _drain(db_session_factory)

    first = await client.post(
        f"{CUST}/commitments/{commitment_id}/deliver",
        json={"delivered_at": "2026-01-15"}, headers=headers,
    )
    assert first.status_code == 200, first.text
    await _drain(db_session_factory)

    second = await client.post(
        f"{CUST}/commitments/{commitment_id}/deliver",
        json={"delivered_at": "2026-01-16"}, headers=headers,
    )
    assert second.status_code == 400
    assert "already" in second.json()["detail"]

    async with db_session_factory() as db:
        commitment = (
            await db.execute(
                select(CustomerCommitment).where(
                    CustomerCommitment.organization_id == org["organization"]["id"],
                    CustomerCommitment.id == commitment_id,
                )
            )
        ).scalar_one()
        assert commitment.status == "delivered"


async def test_event_bus_wires_events_to_engine(client, db_session_factory):
    org = await register_org(client, email="4g5_gov7@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    customer = await _customer(client, headers)

    await client.post(
        f"{CUST}/signals",
        json={"customer_id": customer, "signal_type": "issue", "severity": "high",
              "summary": "SSO down", "source": "support"},
        headers=headers,
    )
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        events = list(
            (
                await db.execute(
                    select(Event).where(
                        Event.organization_id == org_id,
                        Event.name == "customer.signal.recorded",
                    )
                )
            ).scalars().all()
        )
        assert len(events) == 1
        signal = (
            await db.execute(
                select(CustomerSignal).where(
                    CustomerSignal.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert signal.source_event_id == events[0].id
        assert signal.need_key == "sso"


async def test_multi_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="4g5_gov8a@test.co")
    org_b = await register_org(client, email="4g5_gov8b@test.co")

    customer_a = await _customer(client, org_a["headers"], name="Tenant A Co")
    await client.post(
        f"{CUST}/signals",
        json={"customer_id": customer_a, "signal_type": "issue", "severity": "high",
              "summary": "SSO down for tenant A", "source": "support"},
        headers=org_a["headers"],
    )
    await _drain(db_session_factory)

    signals_b = (
        await client.get(f"{CUST}/signals", headers=org_b["headers"])
    ).json()
    assert signals_b["total"] == 0
    assert signals_b["signals"] == []

    health_b = (await client.get(f"{CUST}/health", headers=org_b["headers"])).json()
    assert health_b["total"] == 0
