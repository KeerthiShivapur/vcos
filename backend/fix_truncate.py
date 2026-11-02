with open('tests/acceptance/test_complete_company_e2e.py', 'r') as f:
    content = f.read()

# The duplicate starts at position 75667
dup_start = 75667

# Good content ends at 75667
good_end = 75667

# Verify
print(f'Good content ends at: {good_end}')
print(repr(content[good_end-50:good_end+50]))

# Add the correct method
new_method = '''    @pytest.mark.asyncio
    async def test_five_extraordinary_capabilities(self, db_session, provisioned_company):
        """Test all 5 extraordinary capabilities are operational."""
        org = provisioned_company["organization"]
        admin_user = provisioned_company["admin_user"]
        access = await resolve_caller_access(db_session, organization_id=org.id, user=admin_user)
        
        capabilities_verified = {
            "living_company_memory": False,
            "ask_company_anything": False,
            "future_simulator": False,
            "governed_autonomy": False,
            "company_continuity": False,
        }
        
        # 1. Living Company Memory - timeline events exist
        # Create a decision through canonical_create to generate timeline events
        decision = CompanyDecision(
            organization_id=org.id,
            title="Test Decision for Memory",
            state="approved",
            decision_id="dec-" + uuid.uuid4().hex[:8],
            kind="operational",
            source_event_id="event-" + uuid.uuid4().hex[:8],
            epistemic_status=EpistemicStatus.PROPOSED,
        )
        
        from app.intelligence.canonical_mutation import canonical_create
        
        decision_result = await canonical_create(
            db=db_session,
            caller=access,
            entity=decision,
            provenance={"source_event_id": decision.source_event_id},
        )
        assert decision_result.success
        
        events = await db_session.execute(
            select(CompanyTimelineEvent).where(CompanyTimelineEvent.organization_id == org.id)
        )
        if events.scalars().first():
            capabilities_verified["living_company_memory"] = True
        
        # 2. Ask Company Anything - Company Brain instantiable
        from app.intelligence.company_brain import CompanyBrain
        brain = CompanyBrain()
        if brain is not None:
            capabilities_verified["ask_company_anything"] = True
        
        # 3. Future Simulator - counterfactual service works
        from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
        sim_result = await counterfactual_intelligence_service.create_scenario(
            db=db_session, caller=access,
            scenario_kind="commitment_change",
            subject_type="commitment",
            subject_id="test",
            params={},
            dry_run=True,
        )
        if sim_result is not None and sim_result.get("advisory_only") is True:
            capabilities_verified["future_simulator"] = True
        
        # 4. Governed Autonomy - autonomy proposal creatable
        proposal = AutonomyProposal(
            organization_id=org.id,
            title="Test Autonomy",
            proposal_type="execute_action",
            scope_type="company",
            scope_id=org.id,
            evidence_items=[],
            why="Test autonomy proposal",
            risk_class="propose_only",
            approval_required=False,
            state="proposed",
            fingerprint="fp-" + uuid.uuid4().hex[:16],
            actor_id=access.employee_id,
        )
        
        from app.intelligence.canonical_mutation import canonical_create
        
        proposal_result = await canonical_create(
            db=db_session,
            caller=access,
            entity=proposal,
            provenance={"proposed_by": access.employee_id},
        )
        assert proposal_result.success
        if proposal_result.entity.id:
            capabilities_verified["governed_autonomy"] = True
        
        # 5. Company Continuity - backup/restore works
        backup_result = await backup_service.create_full_backup(
            db=db_session, kind=BackupKind.FULL, organization_id=org.id,
            retention_days=1
        )
        if backup_result.status == BackupStatus.VERIFIED:
            capabilities_verified["company_continuity"] = True
        
        # All 5 capabilities should be verified
        for cap, verified in capabilities_verified.items():
            assert verified, "Capability {} not verified".format(cap)

'''

# Truncate at 75667 and add new method
new_content = content[:75667] + new_method + '\n\n' + content[content.rfind('\n\n\n', 0, len(content)):]

with open('tests/acceptance/test_complete_company_e2e.py', 'w') as f:
    f.write(new_content)

print('Fixed')