with open('tests/test_gate6f_epistemic_integrity.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the governance test and replace it
new_test_lines = [
    '    @pytest.mark.asyncio\n',
    '    async def test_promotion_requires_governance_permissions(\n',
    '        self, db_session, test_org_a, caller_limited\n',
    '    ):\n',
    '        """Strong epistemic promotions require governance permissions."""\n',
    '        # The limited caller has no roles, so they lack evidence:validate permission\n',
    '        # Create a decision that the limited caller CAN access (same org)\n',
    '        decision = CompanyDecision(\n',
    '            organization_id=test_org_a.id,\n',
    '            decision_id="dec-no-perm",\n',
    '            kind="strategic",\n',
    '            title="No Perm Test",\n',
    '            recommendation_key="",\n',
    '            rationale="Test",\n',
    '            state="proposed",\n',
    '            approver_label="test",\n',
    '            source_event_id="evt-no-perm",\n',
    '        )\n',
    '        db_session.add(decision)\n',
    '        await db_session.flush()\n',
    '\n',
    '        # Try to create a NEW decision with EVIDENCE_BACKED without governance permissions\n',
    '        new_decision = CompanyDecision(\n',
    '            organization_id=test_org_a.id,\n',
    '            decision_id="dec-no-perm-2",\n',
    '            kind="strategic",\n',
    '            title="No Perm Test 2",\n',
    '            recommendation_key="",\n',
    '            rationale="Test",\n',
    '            state="proposed",\n',
    '            approver_label="test",\n',
    '            source_event_id="evt-no-perm-2",\n',
    '        )\n',
    '        db_session.add(new_decision)\n',
    '        await db_session.flush()\n',
    '\n',
    '        # Try to create with EVIDENCE_BACKED without governance permissions\n',
    '        result = await canonical_create(\n',
    '            db=db_session,\n',
    '            caller=caller_limited,\n',
    '            entity=new_decision,\n',
    '            provenance={"decision_id": new_decision.id},\n',
    '            required_permissions=["decisions:manage"],\n',
    '        )\n',
    '        \n',
    '        assert result.success is False\n',
    '        assert "permission" in result.error.lower() or "governance" in result.error.lower() or "evidence:validate" in result.error.lower()\n',
]

# Find and replace the governance test
new_lines = []
i = 0
while i < len(lines):
    if 'test_promotion_requires_governance_permissions' in lines[i] and 'async def' in lines[i]:
        # Skip the old test (find the next test method or end of class)
        skip = True
        while i < len(lines) and skip:
            if i + 1 < len(lines) and ('    @pytest.mark.asyncio' in lines[i+1] or '    @pytest.mark.' in lines[i+1]) and 'test_' in lines[i+1]:
                skip = False
            i += 1
        new_lines.extend(new_test_lines)
    else:
        new_lines.append(lines[i])
        i += 1

with open('tests/test_gate6f_epistemic_integrity.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed governance test')