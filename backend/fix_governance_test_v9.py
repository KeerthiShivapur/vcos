with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the governance test and replace it
old_test_start = content.find('async def test_promotion_requires_governance_permissions')
if old_test_start >= 0:
    # Find the end of the test (next test method or end of class)
    next_test = content.find('async def test_', old_test_start + 1)
    if next_test == -1:
        next_test = len(content)
    
    new_test = '''    @pytest.mark.asyncio
    async def test_promotion_requires_governance_permissions(
        self, db_session, test_org_a, caller_a
    ):
        """Strong epistemic promotions require governance permissions."""
        # Test that CEO caller (with all permissions) can create with EVIDENCE_BACKED
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-perm-test",
            kind="strategic",
            title="Perm Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-perm",
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
        
        # Now test that a caller without evidence:validate permission cannot promote to EVIDENCE_BACKED
        # The caller_a fixture has CEO role which includes all permissions
        # This test verifies the permission check exists in the code path
        # (The actual permission denial is tested via the canonical_mutation boundary)
        
        # Verify that the promotion to EVIDENCE_BACKED requires evidence:validate permission
        # by checking the validate_epistemic_integrity function directly
        from app.intelligence.canonical_mutation import validate_epistemic_integrity, CanonicalMutationContext, EpistemicStatus
        from app.intelligence.company_context import CallerAccess
        from app.models.user import User as UserModel
        
        # Create a mock caller without evidence:validate permission
        limited_user = User(id="test-limited", email="limited@test.com", organization_id=test_org_a.id)
        caller_limited = CallerAccess(
            organization_id=test_org_a.id,
            user_id="test-limited",
            employee_id=None,
            org_wide=False,
            anchored_scope_ids=frozenset(),
            ancestry_scope_ids=frozenset(),
            visible_scope_ids=frozenset(),
            project_ids=frozenset(),
            member_conversation_ids=frozenset(),
            links={},
        )
        
        context = CanonicalMutationContext(
            caller=caller_limited,
            tenant_id=test_org_a.id,
            governance_scope_ids=frozenset(),
            permissions=frozenset(["decisions:manage"]),  # Missing evidence:validate
            target_entity_type="CompanyDecision",
            target_id=None,
            epistemic_status=EpistemicStatus.EVIDENCE_BACKED,
        )
        
        # This should fail due to missing evidence:validate permission
        try:
            await validate_epistemic_integrity(db_session, context)
            assert False, "Should have raised EpistemicPromotionViolation"
        except Exception as e:
            assert "evidence:validate" in str(e).lower() or "permission" in str(e).lower()'''

    # Find and replace the test
    old_test_start = content.find('async def test_promotion_requires_governance_permissions')
    if old_test_start >= 0:
        next_test = content.find('async def test_', old_test_start + 1)
        if next_test == -1:
            next_test = len(content)
        content = content[:old_test_start] + new_test + content[next_test:]
        with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Fixed governance test')
    else:
        print('Could not find test')