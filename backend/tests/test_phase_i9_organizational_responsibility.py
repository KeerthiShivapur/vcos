"""
Phase 4I.9 — Organizational Responsibility / Accountability Tests.

Tests cover:
- Responsibility creation with RACI
- Accountability link creation
- Auto-assignment from commitment
- Organizational queries (who is responsible/accountable)
- Capacity analysis
- Organizational integrity detection
- Temporal supersession
- Vocabularies
"""

import hashlib
import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.organizational_responsibility_engine import organizational_responsibility_engine
from app.models.employee import Employee
from app.models.team import Team
from app.models.department import Department
from app.models.role import Role
from app.models.company_intent import (
    CompanyIntent,
)
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    RESPONSIBILITY_TYPES,
    RESPONSIBILITY_SCOPES,
    ACCOUNTABILITY_TYPES,
    RESPONSIBILITY_RACI_ROLES,
)
from tests.conftest import register_org


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

async def _create_minimal_canonical_chain(db_session_factory, org_id: str) -> dict[str, str]:
    """Create minimal intent/goal/objective/initiative chain."""
    async with db_session_factory() as session:
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Test Intent for 4I.9",
            state="active",
            fingerprint=hashlib.sha256(f"intent:4i9-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(intent)
        await session.flush()

        goal = CompanyGoal(
            organization_id=org_id,
            title="Test Goal for 4I.9",
            status="active",
            kind="expansion",
        )
        session.add(goal)
        await session.flush()

        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Test Objective for 4I.9",
            description="Test objective for organizational responsibility testing",
            status="active",
            fingerprint=hashlib.sha256(f"objective:4i9-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(objective)
        await session.flush()

        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Test Initiative for 4I.9",
            description="Test initiative for organizational responsibility testing",
            status="active",
            fingerprint=hashlib.sha256(f"initiative:4i9-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(initiative)
        await session.flush()

        await session.commit()
        return {
            "intent_id": intent.id,
            "goal_id": goal.id,
            "objective_id": objective.id,
            "initiative_id": initiative.id,
        }


async def _create_person(db_session_factory, org_id: str, name: str = "Test Person") -> str:
    """Create a test person."""
    async with db_session_factory() as session:
        first, *rest = name.split(" ", 1)
        last = rest[0] if rest else "User"
        emp = Employee(
            organization_id=org_id,
            email=f"{uuid.uuid4().hex[:8]}@test.co",
            employee_number=f"EMP{uuid.uuid4().hex[:8]}",
            first_name=first,
            last_name=last,
            display_name=name,
            status="active",
        )
        session.add(emp)
        await session.flush()
        await session.commit()
        return emp.id


# -------------------------------------------------------------------------
# Responsibility Creation Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_responsibility_basic(client, db_session_factory):
    """Test creating a basic organizational responsibility."""
    reg = await register_org(client, name=f"Responsibility Corp {uuid.uuid4().hex[:8]}", email=f"resp_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        responsibility = await organizational_responsibility_engine.create_responsibility(
            session, org_id,
            user_id=user_id,
            responsibility_type="responsible",
            scope_type="objective",
            scope_id=chain["objective_id"],
            objective_id=chain["objective_id"],
            person_id=person_id,
            raci_accountable=False,
            raci_responsible=True,
        )

    assert responsibility is not None
    assert responsibility.responsibility_type == "responsible"
    assert responsibility.scope_type == "objective"
    assert responsibility.objective_id == chain["objective_id"]
    assert responsibility.person_id == person_id
    assert responsibility.raci_responsible is True
    assert responsibility.raci_accountable is False


@pytest.mark.asyncio
async def test_create_responsibility_accountable(client, db_session_factory):
    """Test creating an accountable responsibility."""
    reg = await register_org(client, name=f"Accountable Corp {uuid.uuid4().hex[:8]}", email=f"account_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        responsibility = await organizational_responsibility_engine.create_responsibility(
            session, org_id,
            user_id=user_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id="test-commitment-id",
            person_id=person_id,
            raci_accountable=True,
            raci_responsible=False,
        )

    assert responsibility.raci_accountable is True
    assert responsibility.raci_responsible is False


@pytest.mark.asyncio
async def test_create_responsibility_team(client, db_session_factory):
    """Test creating a responsibility assigned to a team."""
    reg = await register_org(client, name=f"Team Responsibility Corp {uuid.uuid4().hex[:8]}", email=f"teamresp_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        team = Team(
            organization_id=org_id,
            name="Engineering Team",
            code="ENG",
        )
        session.add(team)
        await session.flush()
        await session.commit()
        team_id = team.id

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        responsibility = await organizational_responsibility_engine.create_responsibility(
            session, org_id,
            user_id=user_id,
            responsibility_type="responsible",
            scope_type="initiative",
            scope_id=chain["initiative_id"],
            initiative_id=chain["initiative_id"],
            team_id=team_id,
            raci_accountable=False,
            raci_responsible=True,
        )

    assert responsibility.team_id == team_id
    assert responsibility.person_id is None


@pytest.mark.asyncio
async def test_create_responsibility_exact_once(client, db_session_factory):
    """Test exact-once semantics for responsibilities."""
    reg = await register_org(client, name=f"Exact Once Corp {uuid.uuid4().hex[:8]}", email=f"exactonce_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create first
        resp1 = await organizational_responsibility_engine.create_responsibility(
            session, org_id,
            user_id=user_id,
            responsibility_type="responsible",
            scope_type="objective",
            scope_id=chain["objective_id"],
            objective_id=chain["objective_id"],
            person_id=person_id,
            raci_accountable=False,
            raci_responsible=True,
            source_event_id="test.event",
        )

        # Try to create duplicate - should raise
        with pytest.raises(ValueError, match="already exists"):
            await organizational_responsibility_engine.create_responsibility(
                session, org_id,
                user_id=user_id,
                responsibility_type="responsible",
                scope_type="objective",
                scope_id=chain["objective_id"],
                objective_id=chain["objective_id"],
                person_id=person_id,
                raci_accountable=False,
                raci_responsible=True,
                source_event_id="test.event",
            )


@pytest.mark.asyncio
async def test_create_responsibility_raci_validation(client, db_session_factory):
    """Test that at least one RACI role must be true."""
    reg = await register_org(client, name=f"RACI Validation Corp {uuid.uuid4().hex[:8]}", email=f"racival_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)

    async with db_session_factory() as session:
        with pytest.raises(ValueError, match="At least one RACI role must be true"):
            await organizational_responsibility_engine.create_responsibility(
                session, org_id,
                user_id=user_id,
                responsibility_type="responsible",
                scope_type="objective",
                scope_id="test-scope",
                person_id=person_id,
                raci_accountable=False,
                raci_responsible=False,
                raci_consulted=False,
                raci_informed=False,
            )


@pytest.mark.asyncio
async def test_create_responsibility_assignee_validation(client, db_session_factory):
    """Test that at least one assignee must be provided."""
    reg = await register_org(client, name=f"Assignee Validation Corp {uuid.uuid4().hex[:8]}", email=f"assignval_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        with pytest.raises(ValueError, match="At least one of person_id"):
            await organizational_responsibility_engine.create_responsibility(
                session, org_id,
                user_id=user_id,
                responsibility_type="responsible",
                scope_type="objective",
                scope_id="test-scope",
                raci_accountable=False,
                raci_responsible=True,
            )


# -------------------------------------------------------------------------
# Accountability Link Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_accountability_link(client, db_session_factory):
    """Test creating an accountability link."""
    reg = await register_org(client, name=f"Accountability Link Corp {uuid.uuid4().hex[:8]}", email=f"acclink_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=org_id,
            commitment_type="unconditional",
            title="Test Commitment",
            scope_type="objective",
            scope_id=chain["objective_id"],
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            fingerprint=hashlib.sha256(f"commit:acclink:{org_id}".encode()).hexdigest()[:160],
            state="authorized",
        )
        session.add(commitment)
        await session.flush()

        # Create authorization
        auth = CompanyAuthorization(
            organization_id=org_id,
            authorization_type="full",
            title="Test Authorization",
            scope_type="company",
            state="approved",
            fingerprint=hashlib.sha256(f"auth:acclink:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(auth)
        await session.flush()

        # Create responsibility
        resp = OrganizationalResponsibility(
            organization_id=org_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id=commitment.id,
            commitment_id=commitment.id,
            person_id=person_id,
            raci_accountable=True,
            raci_responsible=False,
            valid_from=utcnow().date(),
            fingerprint=hashlib.sha256(f"resp:acclink:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(resp)
        await session.flush()

        # Create link
        link = await organizational_responsibility_engine.create_accountability_link(
            session, org_id,
            commitment_id=commitment.id,
            authorization_id=auth.id,
            responsibility_id=resp.id,
            accountability_type="direct",
        )

    assert link is not None
    assert link.commitment_id == commitment.id
    assert link.authorization_id == auth.id
    assert link.responsibility_id == resp.id
    assert link.accountability_type == "direct"


@pytest.mark.asyncio
async def test_create_accountability_link_exact_once(client, db_session_factory):
    """Test exact-once for accountability links."""
    reg = await register_org(client, name=f"Exact Once Link Corp {uuid.uuid4().hex[:8]}", email=f"exactlink_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        commitment = CompanyCommitment(
            organization_id=org_id,
            commitment_type="unconditional",
            title="Test Commitment",
            scope_type="objective",
            scope_id=chain["objective_id"],
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            fingerprint=hashlib.sha256(f"commit:exactlink:{org_id}".encode()).hexdigest()[:160],
            state="authorized",
        )
        session.add(commitment)
        await session.flush()

        auth = CompanyAuthorization(
            organization_id=org_id,
            authorization_type="full",
            title="Test Authorization",
            scope_type="company",
            state="approved",
            fingerprint=hashlib.sha256(f"auth:exactlink:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(auth)
        await session.flush()

        resp = OrganizationalResponsibility(
            organization_id=org_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id=commitment.id,
            commitment_id=commitment.id,
            person_id=person_id,
            raci_accountable=True,
            raci_responsible=False,
            valid_from=date.today(),
            fingerprint=hashlib.sha256(f"resp:exactlink:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(resp)
        await session.flush()

        # Create first link
        link1 = await organizational_responsibility_engine.create_accountability_link(
            session, org_id,
            commitment_id=commitment.id,
            authorization_id=auth.id,
            responsibility_id=resp.id,
            accountability_type="direct",
        )

        # Try duplicate
        with pytest.raises(ValueError, match="already exists"):
            await organizational_responsibility_engine.create_accountability_link(
                session, org_id,
                commitment_id=commitment.id,
                authorization_id=auth.id,
                responsibility_id=resp.id,
                accountability_type="direct",
            )


# -------------------------------------------------------------------------
# Assign from Commitment Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assign_from_commitment(client, db_session_factory):
    """Test assigning multiple responsibilities from a commitment."""
    reg = await register_org(client, name=f"Assign From Commit Corp {uuid.uuid4().hex[:8]}", email=f"assignfc_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    person2_id = await _create_person(db_session_factory, org_id, "Test Person 2")
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    # Create session manually (not using async with) to control transaction lifecycle
    session = db_session_factory()
    try:
        # Create commitment with authorization
        auth = CompanyAuthorization(
            organization_id=org_id,
            authorization_type="full",
            title="Test Authorization",
            scope_type="company",
            state="approved",
            fingerprint=hashlib.sha256(f"auth:assign:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(auth)
        await session.flush()

        commitment = CompanyCommitment(
            organization_id=org_id,
            commitment_type="conditional",
            title="Test Commitment",
            scope_type="objective",
            scope_id=chain["objective_id"],
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            authorization_id=auth.id,
            fingerprint=hashlib.sha256(f"commit:assign:{org_id}".encode()).hexdigest()[:160],
            state="authorized",
        )
        session.add(commitment)
        await session.flush()

        # Assign responsibilities
        assignments = [
            {
                "responsibility_type": "accountable",
                "scope_type": "commitment",
                "scope_id": commitment.id,
                "person_id": person_id,
                "raci_accountable": True,
                "raci_responsible": False,
            },
            {
                "responsibility_type": "responsible",
                "scope_type": "commitment",
                "scope_id": commitment.id,
                "person_id": person2_id,
                "raci_accountable": False,
                "raci_responsible": True,
            },
            {
                "responsibility_type": "consulted",
                "scope_type": "objective",
                "scope_id": chain["objective_id"],
                "objective_id": chain["objective_id"],
                "person_id": person2_id,
                "raci_consulted": True,
            },
        ]

        created = await organizational_responsibility_engine.assign_responsibilities_from_commitment(
            session, org_id,
            commitment_id=commitment.id,
            user_id=user_id,
            assignments=assignments,
        )

        assert len(created) == 3
        assert created[0].raci_accountable is True
        assert created[1].raci_responsible is True
        assert created[2].raci_consulted is True

        # Commit the session to make changes visible
        await session.commit()
        print("DEBUG: session committed")
        print(f"DEBUG: session.in_transaction() = {session.in_transaction()}")

        # Use a NEW session for verification to see committed data
        from app.models.execution_strategy import AccountabilityLink
        from sqlalchemy import select, text
        async with db_session_factory() as verify_session:
            # Check raw SQL
            result = await verify_session.execute(text("SELECT COUNT(*) FROM accountability_links WHERE organization_id = :oid AND commitment_id = :cid"), {"oid": org_id, "cid": commitment.id})
            count = result.scalar()
            print(f"DEBUG: raw SQL count = {count}")

            # Verify accountability links were created
            result = await verify_session.execute(
                select(AccountabilityLink).where(
                    AccountabilityLink.organization_id == org_id,
                    AccountabilityLink.commitment_id == commitment.id,
                )
            )
            links = result.scalars().all()
            print(f"DEBUG: links = {len(links)}")
            for link in links:
                print(f"  Link: {link.id}, commitment_id={link.commitment_id}")
            assert len(links) == 3
    finally:
        await session.close()


# -------------------------------------------------------------------------
# Query Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_responsibilities_for_commitment(client, db_session_factory):
    """Test getting all responsibilities for a commitment."""
    reg = await register_org(client, name=f"Query Resp Corp {uuid.uuid4().hex[:8]}", email=f"queryresp_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        commitment = CompanyCommitment(
            organization_id=org_id,
            commitment_type="unconditional",
            title="Query Test Commitment",
            scope_type="objective",
            scope_id=chain["objective_id"],
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            fingerprint=hashlib.sha256(f"commit:query:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(commitment)
        await session.flush()

        # Create two responsibilities
        for i in range(2):
            resp = OrganizationalResponsibility(
                organization_id=org_id,
                responsibility_type="responsible",
                scope_type="commitment",
                scope_id=commitment.id,
                commitment_id=commitment.id,
                person_id=person_id,
                raci_responsible=True,
                valid_from=utcnow().date(),
                fingerprint=hashlib.sha256(f"resp:query:{i}:{org_id}".encode()).hexdigest()[:160],
            )
            session.add(resp)
        await session.flush()

        responsibilities = await organizational_responsibility_engine.get_responsibilities_for_commitment(
            session, org_id, commitment.id
        )

    assert len(responsibilities) == 2


@pytest.mark.asyncio
async def test_get_accountability_chain_for_commitment(client, db_session_factory):
    """Test getting full accountability chain for a commitment."""
    reg = await register_org(client, name=f"Chain Query Corp {uuid.uuid4().hex[:8]}", email=f"chainq_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        commitment = CompanyCommitment(
            organization_id=org_id,
            commitment_type="unconditional",
            title="Chain Test Commitment",
            scope_type="objective",
            scope_id=chain["objective_id"],
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            fingerprint=hashlib.sha256(f"commit:chain:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(commitment)
        await session.flush()

        auth = CompanyAuthorization(
            organization_id=org_id,
            authorization_type="full",
            title="Test Auth",
            scope_type="company",
            state="approved",
            fingerprint=hashlib.sha256(f"auth:chain:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(auth)
        await session.flush()

        resp = OrganizationalResponsibility(
            organization_id=org_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id=commitment.id,
            commitment_id=commitment.id,
            person_id=person_id,
            raci_accountable=True,
            valid_from=utcnow().date(),
            fingerprint=hashlib.sha256(f"resp:chain:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(resp)
        await session.flush()

        link = AccountabilityLink(
            organization_id=org_id,
            commitment_id=commitment.id,
            authorization_id=auth.id,
            responsibility_id=resp.id,
            accountability_type="direct",
            valid_from=utcnow().date(),
            fingerprint=hashlib.sha256(f"link:chain:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(link)
        await session.flush()

        chain_result = await organizational_responsibility_engine.get_accountability_chain_for_commitment(
            session, org_id, commitment.id
        )

    assert len(chain_result) == 1
    assert chain_result[0]["commitment_id"] == commitment.id
    assert chain_result[0]["authorization"] is not None
    assert chain_result[0]["responsibility"] is not None
    assert chain_result[0]["assignee"]["type"] == "person"
    assert chain_result[0]["assignee"]["id"] == person_id


@pytest.mark.asyncio
async def test_get_responsibilities_for_person(client, db_session_factory):
    """Test getting all responsibilities for a person."""
    reg = await register_org(client, name=f"Person Resp Corp {uuid.uuid4().hex[:8]}", email=f"personresp_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        for i in range(3):
            resp = OrganizationalResponsibility(
                organization_id=org_id,
                responsibility_type="responsible",
                scope_type="objective",
                scope_id=chain["objective_id"],
                objective_id=chain["objective_id"],
                person_id=person_id,
                raci_responsible=True,
                valid_from=utcnow().date(),
                fingerprint=hashlib.sha256(f"resp:person:{i}:{org_id}".encode()).hexdigest()[:160],
            )
            session.add(resp)
        await session.flush()

        responsibilities = await organizational_responsibility_engine.get_responsibilities_for_person(
            session, org_id, person_id
        )

    assert len(responsibilities) == 3


@pytest.mark.asyncio
async def test_get_accountability_chain_for_person(client, db_session_factory):
    """Test getting all commitments a person is accountable for."""
    reg = await register_org(client, name=f"Person Chain Corp {uuid.uuid4().hex[:8]}", email=f"personchain_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        for i in range(2):
            commitment = CompanyCommitment(
                organization_id=org_id,
                commitment_type="unconditional",
                title=f"Commitment {i}",
                scope_type="objective",
                scope_id=chain["objective_id"],
                intent_id=chain["intent_id"],
                objective_id=chain["objective_id"],
                fingerprint=hashlib.sha256(f"commit:personchain:{i}:{org_id}".encode()).hexdigest()[:160],
            )
            session.add(commitment)
            await session.flush()

            resp = OrganizationalResponsibility(
                organization_id=org_id,
                responsibility_type="accountable" if i == 0 else "responsible",
                scope_type="commitment",
                scope_id=commitment.id,
                commitment_id=commitment.id,
                person_id=person_id,
                raci_accountable=(i == 0),
                raci_responsible=(i == 1),
                valid_from=utcnow().date(),
                fingerprint=hashlib.sha256(f"resp:personchain:{i}:{org_id}".encode()).hexdigest()[:160],
            )
            session.add(resp)
        await session.flush()

        chain_result = await organizational_responsibility_engine.get_accountability_chain_for_person(
            session, org_id, person_id
        )

    assert len(chain_result) == 2
    assert chain_result[0]["raci"]["accountable"] is True
    assert chain_result[1]["raci"]["responsible"] is True


# -------------------------------------------------------------------------
# Organizational Integrity Detection Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_overloaded_people(client, db_session_factory):
    """Test detecting overloaded people."""
    reg = await register_org(client, name=f"Overload Corp {uuid.uuid4().hex[:8]}", email=f"overload_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create 6 accountable responsibilities (threshold = 5)
        for i in range(6):
            commitment = CompanyCommitment(
                organization_id=org_id,
                commitment_type="unconditional",
                title=f"Commitment {i}",
                scope_type="objective",
                scope_id=chain["objective_id"],
                intent_id=chain["intent_id"],
                objective_id=chain["objective_id"],
                fingerprint=hashlib.sha256(f"commit:overload:{i}:{org_id}".encode()).hexdigest()[:160],
            )
            session.add(commitment)
            await session.flush()

            resp = OrganizationalResponsibility(
                organization_id=org_id,
                responsibility_type="accountable",
                scope_type="commitment",
                scope_id=commitment.id,
                commitment_id=commitment.id,
                person_id=person_id,
                raci_accountable=True,
                valid_from=utcnow().date(),
                fingerprint=hashlib.sha256(f"resp:overload:{i}:{org_id}".encode()).hexdigest()[:160],
            )
            session.add(resp)
        await session.flush()

        overloaded = await organizational_responsibility_engine.detect_overloaded_people(
            session, org_id, threshold=5
        )

    assert len(overloaded) == 1
    assert overloaded[0]["person_id"] == person_id
    assert overloaded[0]["accountable_count"] == 6
    assert overloaded[0]["threshold"] == 5


@pytest.mark.asyncio
async def test_detect_orphaned_responsibilities(client, db_session_factory):
    """Test detecting responsibilities not linked to any scope."""
    reg = await register_org(client, name=f"Orphan Corp {uuid.uuid4().hex[:8]}", email=f"orphan_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create orphaned responsibility (no commitment, objective, initiative, project)
        resp = OrganizationalResponsibility(
            organization_id=org_id,
            responsibility_type="responsible",
            scope_type="department",
            scope_id="dept-1",
            department_id="dept-1",
            person_id=person_id,
            raci_responsible=True,
            valid_from=utcnow().date(),
            fingerprint=hashlib.sha256(f"resp:orphan:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(resp)
        await session.flush()

        orphaned = await organizational_responsibility_engine.detect_orphaned_responsibilities(
            session, org_id
        )

    assert len(orphaned) == 1
    assert orphaned[0]["responsibility_id"] == resp.id


@pytest.mark.asyncio
async def test_detect_broken_accountability_chains(client, db_session_factory):
    """Test detecting commitments without accountability chains."""
    reg = await register_org(client, name=f"Broken Chain Corp {uuid.uuid4().hex[:8]}", email=f"broken_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Commitment without accountability links
        commitment = CompanyCommitment(
            organization_id=org_id,
            commitment_type="unconditional",
            title="Broken Chain Commitment",
            scope_type="objective",
            scope_id=chain["objective_id"],
            intent_id=chain["intent_id"],
            objective_id=chain["objective_id"],
            state="authorized",
            fingerprint=hashlib.sha256(f"commit:broken:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(commitment)
        await session.flush()

        broken = await organizational_responsibility_engine.detect_broken_accountability_chains(
            session, org_id
        )

    assert len(broken) == 1
    assert broken[0]["commitment_id"] == commitment.id
    assert broken[0]["issue"] == "no_accountability_links"


# -------------------------------------------------------------------------
# Capacity Analysis Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_person_capacity(client, db_session_factory):
    """Test capacity analysis for a person."""
    reg = await register_org(client, name=f"Capacity Corp {uuid.uuid4().hex[:8]}", email=f"cap_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create commitments with responsibilities
        for i in range(3):
            commitment = CompanyCommitment(
                organization_id=org_id,
                commitment_type="unconditional",
                title=f"Capacity Commitment {i}",
                scope_type="objective",
                scope_id=chain["objective_id"],
                intent_id=chain["intent_id"],
                objective_id=chain["objective_id"],
                state="active" if i < 2 else "authorized",
                fingerprint=hashlib.sha256(f"commit:cap:{i}:{org_id}".encode()).hexdigest()[:160],
            )
            session.add(commitment)
            await session.flush()

            resp = OrganizationalResponsibility(
                organization_id=org_id,
                responsibility_type="accountable" if i == 0 else "responsible",
                scope_type="commitment",
                scope_id=commitment.id,
                commitment_id=commitment.id,
                person_id=person_id,
                raci_accountable=(i == 0),
                raci_responsible=(i > 0),
                valid_from=utcnow().date(),
                fingerprint=hashlib.sha256(f"resp:cap:{i}:{org_id}".encode()).hexdigest()[:160],
            )
            session.add(resp)
        await session.flush()

        analysis = await organizational_responsibility_engine.analyze_person_capacity(
            session, org_id, person_id
        )

    assert analysis["person_id"] == person_id
    assert analysis["accountable_count"] == 1
    assert analysis["responsible_count"] == 2
    assert analysis["active_commitments"] == 3  # 2 active + 1 authorized = 3 active
    assert analysis["workload_score"] == 1 * 3 + 2 * 2  # 7


# -------------------------------------------------------------------------
# Supersession Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supersede_responsibility(client, db_session_factory):
    """Test superseding a responsibility with a new one."""
    reg = await register_org(client, name=f"Supersede Resp Corp {uuid.uuid4().hex[:8]}", email=f"suprresp_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    async with db_session_factory() as session:
        # Create old responsibility
        old_resp = OrganizationalResponsibility(
            organization_id=org_id,
            responsibility_type="responsible",
            scope_type="objective",
            scope_id=chain["objective_id"],
            objective_id=chain["objective_id"],
            person_id=person_id,
            raci_responsible=True,
            valid_from=date.today(),
            fingerprint=hashlib.sha256(f"resp:supersede:old:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(old_resp)
        await session.flush()

        # Create new responsibility
        new_resp = OrganizationalResponsibility(
            organization_id=org_id,
            responsibility_type="accountable",
            scope_type="objective",
            scope_id=chain["objective_id"],
            objective_id=chain["objective_id"],
            person_id=person_id,
            raci_accountable=True,
            raci_responsible=False,
            valid_from=date.today(),
            fingerprint=hashlib.sha256(f"resp:supersede:new:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(new_resp)
        await session.flush()

        old, new = await organizational_responsibility_engine.supersede_responsibility(
            session, org_id, old_resp.id, new_resp.id,
            user_id=user_id, reason="Promoted to accountable"
        )

    assert old.superseded_by_id == new.id
    assert new.supersedes_id == old.id
    assert old.valid_to is not None


# -------------------------------------------------------------------------
# Vocabulary Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_responsibility_types_vocabulary():
    """Test RESPONSIBILITY_TYPES vocabulary is canonical."""
    expected = {"accountable", "responsible", "consulted", "informed", "delegated", "shared", "temporary", "emergency"}
    assert set(RESPONSIBILITY_TYPES) == expected


@pytest.mark.asyncio
async def test_responsibility_scopes_vocabulary():
    """Test RESPONSIBILITY_SCOPES vocabulary is canonical."""
    expected = {"commitment", "objective", "initiative", "project", "department", "team", "role", "person"}
    assert set(RESPONSIBILITY_SCOPES) == expected


@pytest.mark.asyncio
async def test_accountability_types_vocabulary():
    """Test ACCOUNTABILITY_TYPES vocabulary is canonical."""
    expected = {"direct", "delegated", "shared", "oversight"}
    assert set(ACCOUNTABILITY_TYPES) == expected


@pytest.mark.asyncio
async def test_raci_roles_vocabulary():
    """Test RESPONSIBILITY_RACI_ROLES vocabulary is canonical."""
    expected = {"accountable", "responsible", "consulted", "informed"}
    assert set(RESPONSIBILITY_RACI_ROLES) == expected


# -------------------------------------------------------------------------
# API Integration Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_create_responsibility(client, db_session_factory):
    """Test API endpoint for creating responsibility."""
    reg = await register_org(client, name=f"API Resp Corp {uuid.uuid4().hex[:8]}", email=f"apiresp_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)
    chain = await _create_minimal_canonical_chain(db_session_factory, org_id)

    response = await client.post(
        "/api/v1/organizational-responsibility/responsibilities",
        json={
            "responsibility_type": "responsible",
            "scope_type": "objective",
            "scope_id": chain["objective_id"],
            "objective_id": chain["objective_id"],
            "person_id": person_id,
            "raci_accountable": False,
            "raci_responsible": True,
        },
        headers=reg["headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert data["responsibility_type"] == "responsible"
    assert data["person_id"] == person_id


@pytest.mark.asyncio
async def test_api_get_capacity(client, db_session_factory):
    """Test API endpoint for capacity analysis."""
    reg = await register_org(client, name=f"API Cap Corp {uuid.uuid4().hex[:8]}", email=f"apicap_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    person_id = await _create_person(db_session_factory, org_id)

    response = await client.get(
        f"/api/v1/organizational-responsibility/people/{person_id}/capacity",
        headers=reg["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["person_id"] == person_id


@pytest.mark.asyncio
async def test_api_vocabularies(client):
    """Test API vocabulary endpoints."""
    response = await client.get("/api/v1/organizational-responsibility/vocabulary/responsibility-types")
    assert response.status_code == 200
    data = response.json()
    assert "types" in data
    assert "accountable" in data["types"]

    response = await client.get("/api/v1/organizational-responsibility/vocabulary/responsibility-scopes")
    assert response.status_code == 200
    data = response.json()
    assert "scopes" in data
    assert "commitment" in data["scopes"]

    response = await client.get("/api/v1/organizational-responsibility/vocabulary/accountability-types")
    assert response.status_code == 200
    data = response.json()
    assert "types" in data
    assert "direct" in data["types"]

    response = await client.get("/api/v1/organizational-responsibility/vocabulary/raci-roles")
    assert response.status_code == 200
    data = response.json()
    assert "roles" in data
    assert "accountable" in data["roles"]