with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the test that creates a new decision as OBSERVED - should create as EVIDENCE_BACKED then update
old_test = '''    @pytest.mark.asyncio
    async def test_evidence_backed_with_direct_observation_succeeds(
        self, db_session, caller_a, test_org_a
    ):
        """Evidence-backed claim with direct observation confirmation can become OBSERVED."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-direct-obs",
            kind="strategic",
            title="Direct Observation Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-direct",
        )
        db_session.add(decision)
        await db_session.flush()
        set_epistemic_status(decision, EpistemicStatus.OBSERVED)

        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={
                "evidence_ids": ["ev-1"],
                "direct_observation": True,
                "decision_id": decision.id,
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True'''

new_test = '''    @pytest.mark.asyncio
    async def test_evidence_backed_with_direct_observation_succeeds(
        self, db_session, caller_a, test_org_a
    ):
        """Evidence-backed claim with direct observation confirmation can become OBSERVED."""
        decision = CompanyDecision(
            organization_id=test_org_a.id,
            decision_id="dec-direct-obs",
            kind="strategic",
            title="Direct Observation Test",
            recommendation_key="",
            rationale="Test",
            state="proposed",
            approver_label="test",
            source_event_id="evt-direct",
        )
        db_session.add(decision)
        await db_session.flush()
        # Create as EVIDENCE_BACKED first (allowed for new decisions with direct_observation)
        set_epistemic_status(decision, EpistemicStatus.EVIDENCE_BACKED)

        # Create with direct_observation
        result = await canonical_create(
            db=db_session,
            caller=caller_a,
            entity=decision,
            provenance={
                "evidence_ids": ["ev-1"],
                "direct_observation": True,
                "decision_id": decision.id,
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True
        
        # Now update to OBSERVED with direct_observation
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecision",
            entity_id=decision.id,
            updates={"epistemic_status": EpistemicStatus.OBSERVED},
            provenance={
                "decision_id": decision.id,
                "direct_observation": True,
            },
            required_permissions=["decisions:manage"],
        )
        
        assert result.success is True'''

content = content.replace(old_test, new_test)

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed test')