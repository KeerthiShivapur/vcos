with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\test_gate8_5_canonical_organizational_intelligence.py', 'r') as f:
    content = f.read()

# Fix the specific duplicate in the timeline test
content = content.replace(
    '''await db_session.flush()
        
        # Add action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Timeline Action",
            state="completed",
            scope_type="project",
            scope_id="proj-tl",
            fingerprint="action-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="action-tl-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=resp.id,
            assignee_id=test_employee.id,
            state="completed",
            completed_at=utcnow(),
            completed_by=test_employee.id,
        )
        db_session.add(action)
        await db_session.flush()''',
    '''await db_session.flush()
        
        # Add action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Timeline Action",
            state="completed",
            scope_type="project",
            scope_id="proj-tl",
            fingerprint="action-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="action-tl-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=resp.id,
            assignee_id=test_employee.id,
            completed_at=utcnow(),
            completed_by=test_employee.id,
        )
        db_session.add(action)
        await db_session.flush()''')

with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\test_gate8_5_canonical_organizational_intelligence.py', 'w') as f:
    f.write(content)

print('Fixed')