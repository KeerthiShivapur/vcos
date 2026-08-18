"""Slice 4G.5 — model surface: the canonical customer intelligence tables
exist in metadata with the exact-once unique constraints, the canonical
vocabularies are exported, and rows persist with their JSON evidence.

The table names and constraints are the contract: change-driven writes rely
on (organization_id, customer_id, source_event_id) uniqueness.
"""

from sqlalchemy import select

from app.db.database import Base
from app.models.customer_intelligence import (
    COMMITMENT_STATUSES,
    HEALTH_STATES,
    SIGNAL_SEVERITIES,
    SIGNAL_SOURCES,
    SIGNAL_STATUSES,
    SIGNAL_TYPES,
    CustomerCommitment,
    CustomerHealthHistory,
    CustomerHealthRow,
    CustomerOutcome,
    CustomerSignal,
    CustomerTheme,
)
from tests.conftest import register_org


async def test_4g5_tables_registered_in_metadata():
    tables = {
        "customer_signals",
        "customer_themes",
        "customer_commitments",
        "customer_outcomes",
        "customer_health_rows",
        "customer_health_history",
    }
    assert tables <= set(Base.metadata.tables)


async def test_exact_once_unique_constraints():
    def constraints(table_name):
        return {
            tuple(c.columns.keys())
            for c in Base.metadata.tables[table_name].constraints
            if c.__class__.__name__ == "UniqueConstraint"
        }

    assert ("organization_id", "customer_id", "source_event_id") in constraints(
        "customer_signals"
    )
    assert ("organization_id", "customer_id", "source_event_id") in constraints(
        "customer_commitments"
    )
    assert ("organization_id", "customer_id", "source_event_id") in constraints(
        "customer_outcomes"
    )
    assert ("organization_id", "customer_id", "source_event_id") in constraints(
        "customer_health_history"
    )
    assert ("organization_id", "customer_id") in constraints("customer_health_rows")
    assert ("organization_id", "key") in constraints("customer_themes")


async def test_canonical_vocabularies_exported():
    assert "churn_risk" in SIGNAL_TYPES
    assert "critical" in SIGNAL_SEVERITIES
    assert "interview" in SIGNAL_SOURCES
    assert "delivered" in COMMITMENT_STATUSES
    assert "at_risk" in HEALTH_STATES
    assert "acknowledged" in SIGNAL_STATUSES


async def test_rows_persist_with_json_evidence(client, db_session_factory):
    org = await register_org(client, email="4g5_mod4@test.co")
    org_id = org["organization"]["id"]

    from app.models.customer import Customer

    async with db_session_factory() as db:
        customer = Customer(organization_id=org_id, company_name="Model Co",
                            status="customer", segment="mid_market", tier="basic")
        db.add(customer)
        await db.flush()

        signal = CustomerSignal(
            organization_id=org_id, customer_id=customer.id,
            signal_type="issue", severity="high", need_key="sso",
            title="SSO login fails", source="support",
            source_event_id="evt-model-1",
        )
        db.add(signal)
        await db.flush()

        theme = CustomerTheme(
            organization_id=org_id, key="sso", title="single sign-on",
            occurrences=1, customer_count=1, open_count=1,
            high_severity_count=1,
            signal_ids_json=[signal.id], customer_ids_json=[customer.id],
            trend="stable",
        )
        db.add(theme)

        commitment = CustomerCommitment(
            organization_id=org_id, customer_id=customer.id,
            summary="SSO rollout", expected_at=__import__("datetime").date(2026, 12, 31),
            status="pending", capability="sso",
            source_event_id="evt-model-2",
        )
        db.add(commitment)

        health = CustomerHealthRow(
            organization_id=org_id, customer_id=customer.id,
            state="concerned", score=60,
            reasons_json=["1 unresolved critical signal(s)"],
            positives_json=[], factors_json={"signals": 1},
        )
        db.add(health)

        history = CustomerHealthHistory(
            organization_id=org_id, customer_id=customer.id,
            state="healthy", score=100,
            reasons_json=[], positives_json=[],
            source_event_id="evt-model-3",
        )
        db.add(history)

        outcome = CustomerOutcome(
            organization_id=org_id, customer_id=customer.id,
            metric_kind="login_success", baseline=70, target=95, actual=90,
            signal_id=signal.id, source_event_id="evt-model-4",
        )
        db.add(outcome)
        await db.commit()

        saved = (
            await db.execute(
                select(CustomerSignal).where(
                    CustomerSignal.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert saved.title == "SSO login fails"
        assert saved.source_event_id == "evt-model-1"
        assert saved.need_key == "sso"

        theme_saved = (
            await db.execute(
                select(CustomerTheme).where(
                    CustomerTheme.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert theme_saved.signal_ids_json == [signal.id]
        assert theme_saved.customer_ids_json == [customer.id]
        assert theme_saved.trend == "stable"
