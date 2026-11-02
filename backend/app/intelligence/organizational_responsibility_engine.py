"""
Phase 4I.9 — Organizational Responsibility / Accountability Engine.

This engine implements the explicit link between people/teams/roles and the
objectives/commitments they are responsible/accountable for.

Key principles:
- Governance-first: scope resolved before any retrieval
- Responsibility ≠ Permission ≠ Role ≠ Authorization ≠ Accountability
- Explicit RACI: accountable, responsible, consulted, informed
- Temporal: valid_from/valid_to with supersession chain
- Scoped: person | role | team | department
- Provenance: traces back to Commitment → Authorization → Decision
- People are nodes in the same canonical company graph (NOT a separate HR module)

This is NOT a parallel HR/people graph. People are first-class nodes in the
same canonical company operating fabric.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, date, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.team import Team
from app.models.department import Department
from app.models.role import Role
from app.models.company_intent import CompanyIntent
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
from app.models.organizational_learning import OrganizationalLearning
from app.intelligence.governed_commitment_engine import governed_commitment_engine
from app.intelligence.company_planning_context_engine import company_planning_context_engine


class OrganizationalResponsibilityEngine:
    """
    Organizational Responsibility / Accountability Engine — the canonical bridge
    from Governed Commitments to People/Teams/Departments.

    This engine:
    1. Creates/maintains OrganizationalResponsibility records
    2. Creates/maintains AccountabilityLink records (Commitment → Authorization → Responsibility → Person)
    3. Provides organizational queries (who is responsible, who is accountable, capacity analysis)
    4. Detects organizational integrity issues (overloaded, orphaned, broken chains)
    5. Integrates with CompanyBrain for organizational queries
    """

    # -------------------------------------------------------------------------
    # Responsibility Creation
    # -------------------------------------------------------------------------

    async def create_responsibility(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        user_id: str,
        responsibility_type: str = "responsible",
        scope_type: str = "objective",
        scope_id: Optional[str] = None,
        objective_id: Optional[str] = None,
        initiative_id: Optional[str] = None,
        project_id: Optional[str] = None,
        commitment_id: Optional[str] = None,
        person_id: Optional[str] = None,
        team_id: Optional[str] = None,
        department_id: Optional[str] = None,
        role_id: Optional[str] = None,
        raci_accountable: bool = False,
        raci_responsible: bool = True,
        raci_consulted: bool = False,
        raci_informed: bool = False,
        valid_from: Optional[date] = None,
        valid_to: Optional[date] = None,
        source_event_id: Optional[str] = None,
        source_decision_id: Optional[str] = None,
        source_commitment_id: Optional[str] = None,
    ) -> OrganizationalResponsibility:
        """
        Create a new organizational responsibility with full governance integration.
        """
        if responsibility_type not in RESPONSIBILITY_TYPES:
            raise ValueError(f"Invalid responsibility type: {responsibility_type}")
        if scope_type not in RESPONSIBILITY_SCOPES:
            raise ValueError(f"Invalid scope type: {scope_type}")

        # At least one RACI role must be true
        if not (raci_accountable or raci_responsible or raci_consulted or raci_informed):
            raise ValueError("At least one RACI role must be true")

        # At least one assignee must be provided
        if not any([person_id, team_id, department_id, role_id]):
            raise ValueError("At least one of person_id, team_id, department_id, or role_id must be provided")

        # Validate scope references
        if scope_type == "objective" and objective_id:
            obj = await db.get(CompanyObjective, objective_id)
            if not obj or obj.organization_id != organization_id:
                raise ValueError("Invalid objective ID")
        elif scope_type == "initiative" and initiative_id:
            init = await db.get(CompanyInitiative, initiative_id)
            if not init or init.organization_id != organization_id:
                raise ValueError("Invalid initiative ID")
        elif scope_type == "project" and project_id:
            from app.models.project import Project
            proj = await db.get(Project, project_id)
            if not proj or proj.organization_id != organization_id:
                raise ValueError("Invalid project ID")
        elif scope_type == "commitment" and commitment_id:
            commit = await db.get(CompanyCommitment, commitment_id)
            if not commit or commit.organization_id != organization_id:
                raise ValueError("Invalid commitment ID")

        # Validate assignees exist
        if person_id:
            emp = await db.get(Employee, person_id)
            if not emp or emp.organization_id != organization_id:
                raise ValueError("Invalid person ID")
        if team_id:
            team = await db.get(Team, team_id)
            if not team or team.organization_id != organization_id:
                raise ValueError("Invalid team ID")
        if department_id:
            dept = await db.get(Department, department_id)
            if not dept or dept.organization_id != organization_id:
                raise ValueError("Invalid department ID")
        if role_id:
            role = await db.get(Role, role_id)
            if not role or role.organization_id != organization_id:
                raise ValueError("Invalid role ID")

        # Build fingerprint for exact-once
        fingerprint_data = f"{organization_id}:{responsibility_type}:{scope_type}:{scope_id or ''}:{person_id or ''}:{team_id or ''}:{department_id or ''}:{role_id or ''}:{valid_from or ''}:{valid_to or ''}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        # Check exact-once
        existing = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == organization_id,
                OrganizationalResponsibility.fingerprint == fingerprint,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Responsibility with this fingerprint already exists")

        if valid_from is None:
            valid_from = utcnow().date()

        responsibility = OrganizationalResponsibility(
            organization_id=organization_id,
            responsibility_type=responsibility_type,
            scope_type=scope_type,
            scope_id=scope_id,
            objective_id=objective_id,
            initiative_id=initiative_id,
            project_id=project_id,
            commitment_id=commitment_id,
            person_id=person_id,
            team_id=team_id,
            department_id=department_id,
            role_id=role_id,
            raci_accountable=raci_accountable,
            raci_responsible=raci_responsible,
            raci_consulted=raci_consulted,
            raci_informed=raci_informed,
            valid_from=valid_from,
            valid_to=valid_to,
            source_event_id=source_event_id,
            fingerprint=fingerprint,
        )
        db.add(responsibility)
        await db.flush()

        return responsibility

    # -------------------------------------------------------------------------
    # Accountability Link Creation
    # -------------------------------------------------------------------------

    async def create_accountability_link(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        commitment_id: str,
        authorization_id: str,
        responsibility_id: str,
        accountability_type: str = "direct",
        source_event_id: Optional[str] = None,
    ) -> AccountabilityLink:
        """
        Create an accountability link bridging Commitment → Authorization → Responsibility.
        """
        if accountability_type not in ACCOUNTABILITY_TYPES:
            raise ValueError(f"Invalid accountability type: {accountability_type}")

        # Verify all three entities exist
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            raise ValueError("Invalid commitment ID")

        auth = await db.get(CompanyAuthorization, authorization_id)
        if not auth or auth.organization_id != organization_id:
            raise ValueError("Invalid authorization ID")

        responsibility = await db.get(OrganizationalResponsibility, responsibility_id)
        if not responsibility or responsibility.organization_id != organization_id:
            raise ValueError("Invalid responsibility ID")

        # Exact-once fingerprint
        fingerprint_data = f"{organization_id}:{commitment_id}:{authorization_id}:{responsibility_id}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]

        # Check exact-once
        existing = await db.execute(
            select(AccountabilityLink).where(
                AccountabilityLink.organization_id == organization_id,
                AccountabilityLink.fingerprint == fingerprint,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Accountability link with this fingerprint already exists")

        link = AccountabilityLink(
            organization_id=organization_id,
            commitment_id=commitment_id,
            authorization_id=authorization_id,
            responsibility_id=responsibility_id,
            accountability_type=accountability_type,
            valid_from=utcnow().date(),
            source_event_id=source_event_id,
            fingerprint=fingerprint,
        )
        db.add(link)
        await db.flush()

        return link

    # -------------------------------------------------------------------------
    # Auto-create responsibilities from commitment authorization
    # -------------------------------------------------------------------------

    async def assign_responsibilities_from_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        commitment_id: str,
        user_id: str,
        assignments: list[dict],
        source_event_id: Optional[str] = None,
    ) -> list[OrganizationalResponsibility]:
        """
        Assign multiple responsibilities from a commitment authorization.

        Each assignment dict should contain:
        - responsibility_type: accountable|responsible|consulted|informed
        - scope_type: commitment|objective|initiative|project|department|team|role|person
        - scope_id (or objective_id/initiative_id/project_id)
        - person_id | team_id | department_id | role_id
        - raci_* flags
        - valid_from, valid_to
        """
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != organization_id:
            raise ValueError("Invalid commitment ID")

        # Get the authorization if conditional
        authorization_id = commitment.authorization_id

        created = []
        for assignment in assignments:
            responsibility = await self.create_responsibility(
                db, organization_id,
                user_id=user_id,
                responsibility_type=assignment.get("responsibility_type", "responsible"),
                scope_type=assignment.get("scope_type", "commitment"),
                scope_id=assignment.get("scope_id"),
                objective_id=assignment.get("objective_id"),
                initiative_id=assignment.get("initiative_id"),
                project_id=assignment.get("project_id"),
                commitment_id=commitment_id,
                person_id=assignment.get("person_id"),
                team_id=assignment.get("team_id"),
                department_id=assignment.get("department_id"),
                role_id=assignment.get("role_id"),
                raci_accountable=assignment.get("raci_accountable", False),
                raci_responsible=assignment.get("raci_responsible", True),
                raci_consulted=assignment.get("raci_consulted", False),
                raci_informed=assignment.get("raci_informed", False),
                valid_from=assignment.get("valid_from"),
                valid_to=assignment.get("valid_to"),
                source_event_id=source_event_id,
                source_commitment_id=commitment_id,
            )
            created.append(responsibility)

            # Create accountability link if authorization exists
            if authorization_id:
                print(f"DEBUG ENGINE: Creating link for commitment_id={commitment_id}, auth_id={authorization_id}, resp_id={responsibility.id}")
                link = await self.create_accountability_link(
                    db, organization_id,
                    commitment_id=commitment_id,
                    authorization_id=authorization_id,
                    responsibility_id=responsibility.id,
                    accountability_type="direct",
                    source_event_id=source_event_id,
                )
                print(f"DEBUG ENGINE: Link created successfully, link.id={link.id}")
            else:
                print(f"DEBUG ENGINE: No authorization_id, skipping link creation")

        return created

    # -------------------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------------------

    async def get_responsibility(
        self,
        db: AsyncSession,
        organization_id: str,
        responsibility_id: str,
    ) -> Optional[OrganizationalResponsibility]:
        """Get a responsibility by ID."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.id == responsibility_id,
                OrganizationalResponsibility.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_accountability_link(
        self,
        db: AsyncSession,
        organization_id: str,
        link_id: str,
    ) -> Optional[AccountabilityLink]:
        """Get an accountability link by ID."""
        result = await db.execute(
            select(AccountabilityLink).where(
                AccountabilityLink.id == link_id,
                AccountabilityLink.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_responsibilities_for_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
    ) -> list[OrganizationalResponsibility]:
        """Get all responsibilities for a commitment."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == organization_id,
                OrganizationalResponsibility.commitment_id == commitment_id,
            )
        )
        return list(result.scalars().all())

    async def get_accountability_chain_for_commitment(
        self,
        db: AsyncSession,
        organization_id: str,
        commitment_id: str,
    ) -> list[dict]:
        """Get full accountability chain for a commitment."""
        # Get accountability links
        links_result = await db.execute(
            select(AccountabilityLink).where(
                AccountabilityLink.organization_id == organization_id,
                AccountabilityLink.commitment_id == commitment_id,
            )
        )
        links = links_result.scalars().all()

        chain = []
        for link in links:
            responsibility = await db.get(OrganizationalResponsibility, link.responsibility_id)
            authorization = await db.get(CompanyAuthorization, link.authorization_id)

            chain.append({
                "commitment_id": commitment_id,
                "authorization": authorization,
                "responsibility": responsibility,
                "accountability_type": link.accountability_type,
                "assignee": self._get_assignee_info(responsibility),
            })
        return chain

    def _get_assignee_info(self, responsibility: OrganizationalResponsibility) -> dict:
        """Get human-readable assignee info."""
        if responsibility.person_id:
            return {"type": "person", "id": responsibility.person_id}
        elif responsibility.team_id:
            return {"type": "team", "id": responsibility.team_id}
        elif responsibility.department_id:
            return {"type": "department", "id": responsibility.department_id}
        elif responsibility.role_id:
            return {"type": "role", "id": responsibility.role_id}
        return {"type": "unassigned", "id": None}

    async def get_responsibilities_for_person(
        self,
        db: AsyncSession,
        organization_id: str,
        person_id: str,
    ) -> list[OrganizationalResponsibility]:
        """Get all responsibilities for a person."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == organization_id,
                OrganizationalResponsibility.person_id == person_id,
            )
        )
        return list(result.scalars().all())

    async def get_accountability_chain_for_person(
        self,
        db: AsyncSession,
        organization_id: str,
        person_id: str,
    ) -> list[dict]:
        """Get all commitments a person is accountable for (via responsibilities)."""
        responsibilities = await self.get_responsibilities_for_person(db, organization_id, person_id)

        chain = []
        for resp in responsibilities:
            if resp.commitment_id:
                commitment = await db.get(CompanyCommitment, resp.commitment_id)
                if commitment:
                    chain.append({
                        "commitment": commitment,
                        "responsibility": resp,
                        "raci": {
                            "accountable": resp.raci_accountable,
                            "responsible": resp.raci_responsible,
                            "consulted": resp.raci_consulted,
                            "informed": resp.raci_informed,
                        }
                    })
        return chain

    # -------------------------------------------------------------------------
    # Organizational Integrity Detection
    # -------------------------------------------------------------------------

    async def detect_overloaded_people(
        self,
        db: AsyncSession,
        organization_id: str,
        threshold: int = 5,
    ) -> list[dict]:
        """Detect people with too many accountable responsibilities."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == organization_id,
                OrganizationalResponsibility.raci_accountable == True,
            )
        )
        responsibilities = result.scalars().all()

        person_counts = {}
        for resp in responsibilities:
            if resp.person_id:
                person_counts[resp.person_id] = person_counts.get(resp.person_id, 0) + 1

        overloaded = []
        for person_id, count in person_counts.items():
            if count > threshold:
                person = await db.get(Employee, person_id)
                overloaded.append({
                    "person_id": person_id,
                    "person_name": person.full_name if person else "Unknown",
                    "accountable_count": count,
                    "threshold": threshold,
                })
        return overloaded

    async def detect_orphaned_responsibilities(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> list[dict]:
        """Detect responsibilities not linked to any commitment or objective."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == organization_id,
                OrganizationalResponsibility.commitment_id == None,
                OrganizationalResponsibility.objective_id == None,
                OrganizationalResponsibility.initiative_id == None,
                OrganizationalResponsibility.project_id == None,
            )
        )
        orphaned = result.scalars().all()

        return [
            {
                "responsibility_id": r.id,
                "responsibility_type": r.responsibility_type,
                "scope_type": r.scope_type,
                "scope_id": r.scope_id,
                "assignee": self._get_assignee_info(r),
            }
            for r in orphaned
        ]

    async def detect_broken_accountability_chains(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> list[dict]:
        """Detect commitments without full accountability chains."""
        # Get all commitments
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == organization_id,
                CompanyCommitment.state.in_(["authorized", "active"]),
            )
        )
        commitments = commitments_result.scalars().all()

        broken = []
        for commit in commitments:
            links_result = await db.execute(
                select(AccountabilityLink).where(
                    AccountabilityLink.organization_id == organization_id,
                    AccountabilityLink.commitment_id == commit.id,
                )
            )
            links = links_result.scalars().all()

            if not links:
                broken.append({
                    "commitment_id": commit.id,
                    "commitment_title": commit.title,
                    "issue": "no_accountability_links",
                })
            else:
                # Check if all links have valid responsibilities
                for link in links:
                    resp = await db.get(OrganizationalResponsibility, link.responsibility_id)
                    if not resp:
                        broken.append({
                            "commitment_id": commit.id,
                            "commitment_title": commit.title,
                            "issue": "missing_responsibility",
                            "link_id": link.id,
                        })
        return broken

    # -------------------------------------------------------------------------
    # Capacity Analysis
    # -------------------------------------------------------------------------

    async def analyze_person_capacity(
        self,
        db: AsyncSession,
        organization_id: str,
        person_id: str,
    ) -> dict:
        """Analyze capacity for a specific person."""
        responsibilities = await self.get_responsibilities_for_person(db, organization_id, person_id)

        accountable_count = sum(1 for r in responsibilities if r.raci_accountable)
        responsible_count = sum(1 for r in responsibilities if r.raci_responsible)
        consulted_count = sum(1 for r in responsibilities if r.raci_consulted)
        informed_count = sum(1 for r in responsibilities if r.raci_informed)

        # Get commitments
        commitment_ids = [r.commitment_id for r in responsibilities if r.commitment_id]
        commitments = []
        for cid in commitment_ids:
            c = await db.get(CompanyCommitment, cid)
            if c:
                commitments.append(c)

        # Calculate workload score (simple heuristic)
        workload_score = accountable_count * 3 + responsible_count * 2 + consulted_count * 1 + informed_count * 0.5

        person = await db.get(Employee, person_id)

        return {
            "person_id": person_id,
            "person_name": person.full_name if person else "Unknown",
            "accountable_count": accountable_count,
            "responsible_count": responsible_count,
            "consulted_count": consulted_count,
            "informed_count": informed_count,
            "total_responsibilities": len(responsibilities),
            "active_commitments": len([c for c in commitments if c.state in ("authorized", "active")]),
            "workload_score": workload_score,
            "is_overloaded": workload_score > 15,  # configurable threshold
            "commitments": [{"id": c.id, "title": c.title, "state": c.state} for c in commitments],
        }

    # -------------------------------------------------------------------------
    # Supersession / Temporal
    # -------------------------------------------------------------------------

    async def supersede_responsibility(
        self,
        db: AsyncSession,
        organization_id: str,
        old_responsibility_id: str,
        new_responsibility_id: str,
        *,
        user_id: str,
        reason: str,
        source_event_id: Optional[str] = None,
    ) -> tuple[OrganizationalResponsibility, OrganizationalResponsibility]:
        """Supersede a responsibility with a new one, maintaining temporal chain."""
        old_resp = await db.get(OrganizationalResponsibility, old_responsibility_id)
        new_resp = await db.get(OrganizationalResponsibility, new_responsibility_id)

        if not old_resp or old_resp.organization_id != organization_id:
            raise ValueError("Old responsibility not found")
        if not new_resp or new_resp.organization_id != organization_id:
            raise ValueError("New responsibility not found")

        # Link supersession chain
        old_resp.superseded_by_id = new_resp.id
        new_resp.supersedes_id = old_resp.id

        # Update validity
        old_resp.valid_to = utcnow().date()

        # Record in strategic history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=organization_id,
            entity_type="organizational_responsibility",
            entity_id=old_responsibility_id,
            entity_label=old_resp.title[:300] if hasattr(old_resp, 'title') else f"Responsibility {old_resp.id}",
            field="superseded_by",
            old_value=None,
            new_value=new_responsibility_id,
            reason=reason,
            source_event_id=source_event_id or "responsibility.superseded",
            changed_at=utcnow(),
        )
        db.add(history)

        await db.flush()
        return old_resp, new_resp


organizational_responsibility_engine = OrganizationalResponsibilityEngine()