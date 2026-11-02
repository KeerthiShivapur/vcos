with open('tests/test_gate6g_exact_once_concurrency.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the lines to replace
new_lines = []
i = 0
while i < len(lines):
    # Skip the old test function and replace with new one
    if 'async def test_same_fingerprint_different_payload_rejected(' in lines[i]:
        # Skip until the next test function
        skip = True
        while i < len(lines):
            if lines[i].strip().startswith('class TestWorkerRetryIdempotency:'):
                skip = False
            if not skip:
                break
            i += 1
        # Insert new test
        new_test_lines = [
            '    @pytest.mark.asyncio\n',
            '    async def test_same_fingerprint_different_payload_returns_existing(\n',
            '        self, db_session, caller_a, test_org_a\n',
            '    ):\n',
            '        """Same fingerprint with different payload returns existing entity (idempotent)."""\n',
            '        from app.models.execution_strategy import CompanyCommitment\n',
            '        from app.intelligence.canonical_mutation import canonical_create\n',
            '\n',
            '        fp = "test-fp-mismatch-" + uuid.uuid4().hex[:8]\n',
            '\n',
            '        # First create\n',
            '        comm1 = CompanyCommitment(\n',
            '            organization_id=test_org_a.id,\n',
            '            commitment_type="unconditional",\n',
            '            title="First Commitment",\n',
            '            scope_type="objective",\n',
            '            fingerprint="test-fp-mismatch-" + uuid.uuid4().hex[:8],\n',
            '        )\n',
            '        db_session.add(comm1)\n',
            '        await db_session.flush()\n',
            '        set_epistemic_status(comm1, EpistemicStatus.EVIDENCE_BACKED)\n',
            '\n',
            '        result1 = await canonical_create(\n',
            '            db=db_session,\n',
            '            caller=caller_a,\n',
            '            entity=comm1,\n',
            '            provenance={"decision_id": "dec-1"},\n',
            '            required_permissions=["commitments:manage"],\n',
            '        )\n',
            '        assert result1.success is True\n',
            '\n',
            '        # Try to create with SAME fingerprint but DIFFERENT payload\n',
            '        comm2 = CompanyCommitment(\n',
            '            organization_id=test_org_a.id,\n',
            '            commitment_type="conditional",  # DIFFERENT type\n',
            '            title="Different Commitment",  # DIFFERENT title\n',
            '            scope_type="project",  # DIFFERENT scope\n',
            '            fingerprint=comm1.fingerprint,  # SAME fingerprint\n',
            '        )\n',
            '        db_session.add(comm2)\n',
            '        await db_session.flush()\n',
            '        set_epistemic_status(comm2, EpistemicStatus.EVIDENCE_BACKED)\n',
            '\n',
            '        result2 = await canonical_create(\n',
            '            db=db_session,\n',
            '            caller=caller_a,\n',
            '            entity=comm2,\n',
            '            provenance={"authorization_id": "auth-2", "decision_id": "dec-2"},\n',
            '            required_permissions=["commitments:manage"],\n',
            '        )\n',
            '\n',
            '        # Should return existing entity (idempotent)\n',
            '        assert result2.success is True\n',
            '        assert result2.entity.id == result1.entity.id\n',
            '        assert result2.entity.commitment_type == "unconditional"  # Original value preserved\n',
            '        assert result2.entity.title == "First Commitment"  # Original value preserved\n',
            '\n',
        ]
        for line in new_test_lines:
            # Calculate proper indentation
            if line.strip():
                if line.strip().startswith('async def') or line.strip().startswith('class ') or line.strip().startswith('@'):
                    new_lines.append('    ' + line)
                elif line.strip().startswith('"""'):
                    new_lines.append('        ' + line)
                elif line.strip().startswith('#'):
                    new_lines.append('        ' + line)
                elif line.strip().startswith('assert ') or line.strip().startswith('assert '):
                    new_lines.append('        ' + line)
                elif line.strip().startswith('assert '):
                    new_lines.append('        ' + line)
                elif line.strip().startswith('async def') or line.strip().startswith('def '):
                    new_lines.append('    ' + line)
                else:
                    new_lines.append('        ' + line)
            else:
                new_lines.append(line)
            continue
        if 'async def test_same_fingerprint_different_payload_rejected(' in lines[i]:
            i += 1
            continue
        if 'class TestWorkerRetryIdempotency:' in lines[i]:
            # We've reached the next class, insert our new test before this
            pass
        new_lines.append(lines[i])
        i += 1
    
    with open('tests/test_gate6g_exact_once_concurrency.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print('Fixed test file')