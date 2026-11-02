with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the governance test - the limited caller needs to be able to access the decision
# The issue is that the limited caller can't access the decision at all
# We need to give the limited caller access to the decision first
old_test = '''    @pytest.mark.asyncio
    async def test_promotion_requires_governance_permissions(
        self, db_session, test_org_a, caller_limited
    ):
        """Strong epistemic promotions require governance permissions."""
        # The limited caller has no roles, so they lack evidence:validate permission
        # Create a decision that the limited caller CAN access (same org)
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-no-perm",
            kind="strategic",
            title="No Perm Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-no-perm",
        )
        db_session.add(decision)
        await db_session.flush()

        # Try to create a NEW decision with EVIDENCE_BACKED without governance permissions
        new_decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-no-perm-2",
            kind="strategic",
            title="No Perm Test 2",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-no-perm-2",
        )
        db_session.add(new_decision)
        await db_session.flush()

        # Try to create with EVIDENCE_BACKED without governance permissions
        result = await canonical_create(
            db=db_session,
            caller=caller_limited,
            entity=new_decision,
            provenance={"decision_id": new_decision.id},
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is False
        assert "permission" in result.error.lower() or "governance" in result.error.lower() or "evidence:validate" in result.error.lower()'''

new_test = '''    @pytest.mark.asyncio
    async def test_promotion_requires_governance_permissions(
        self, db_session, test_org_a, caller_limited
    ):
        """Strong epistemic promotions require governance permissions."""
        # The limited caller has no roles, so they lack evidence:validate permission
        # Create a decision that the limited caller CAN access (same org)
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-no-perm",
            kind="strategic",
            title="No Perm Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-no-perm",
        )
        db_session.add(decision)
        await db_session.flush()

        # First, grant the limited caller access to this specific decision
        # by creating a scope and assigning it (simulating project-level access)
        from app.models.governance import GovernanceScope, GovernanceScopeType
        from app.services.governance_service import governance_service
        
        scope = GovernanceScope(
            organization_id=test_org_a.id,
            scope_type=GovernanceScopeType.PROJECT,
            name="Test Project",
            entity_id=decision.id,
        )
        db_session.add(scope)
        await db_session.flush()
        
        # Assign the limited caller to this scope
        from app.models.governance import RoleAssignment
        # Get a basic role
        role = (await db_session.execute(
            select(Role).where(Role.organization_id == test_org_a.id, Role.code == "member")
        )).scalars().first()
        
        if role:
            role_assignment = RoleAssignment(
                user_id=caller_limited.user_id,
                role_id=role.id,
                organization_id=test_org_a.id,
                scope_id=scope.id,
            )
            db_session.add(role_assignment)
            await db_session.flush()
            
            # Refresh the caller's access
            caller_limited = await resolve_caller_access(
                db_session, organization_id=test_org_a.id, user=caller_limited
            )

        # Try to create a NEW decision with EVIDENCE_BACKED without governance permissions
        new_decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-no-perm-2",
            kind="strategic",
            title="No Perm Test 2",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-no-perm-2",
        )
        db_session.add(new_decision)
        await db_session.flush()

        # Try to create with EVIDENCE_BACKED without governance permissions
        result = await canonical_create(
            db=db_session,
            caller=caller_limited,
            entity=new_decision,
            provenance={"decision_id": new_decision.id},
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is False
        assert "permission" in result.error.lower() or "governance" in result.error.lower() or "evidence:validate" in result.error.lower()'''

content = content.replace(old_test, new_test)

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed governance test')