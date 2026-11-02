with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Simplify the governance test
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
        self, db_session, test_org_a, caller_a, caller_limited
    ):
        """Strong epistemic promotions require governance permissions."""
        # The limited caller has no roles, so they lack evidence:validate permission
        # Create a decision with CEO caller (has all permissions)
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

        # CEO caller creates with EVIDENCE_BACKED - should succeed
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={"decision_id": decision.id},
            required_permissions=["decisions:manage"],
        )
        assert result.success is True

        # Now try with limited caller - should fail due to missing evidence:validate permission
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

content = content.replace(
    '''    @pytest.mark.asyncio
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
        assert "permission" in result.error.lower() or "governance" in result.error.lower() or "evidence:validate" in result.error.lower()''',
    '''    @pytest.mark.asyncio
    async def test_promotion_requires_governance_permissions(
        self, db_session, test_org_a, caller_a, caller_limited
    ):
        """Strong epistemic promotions require governance permissions."""
        # The limited caller has no roles, so they lack evidence:validate permission
        # Create a decision with CEO caller (has all permissions)
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

        # CEO caller creates with EVIDENCE_BACKED - should succeed
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={"decision_id": decision.id},
            required_permissions=["decisions:manage"],
        )
        assert result.success is True

        # Now try with limited caller - should fail due to missing evidence:validate permission
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
        assert "permission" in result.error.lower() or "governance" in result.error.lower() or "evidence:validate" in result.error.lower()''', content)

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed governance test')