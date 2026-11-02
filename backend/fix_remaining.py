with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix Team creation - remove status field
content = content.replace(
    '''            team = Team(
                    id=self._create_id("team-"),
                    organization_id=self.context.organization_id,
                    department_id=dept.id,
                    name=f"{dept.name} Team {i+1}",
                    description=f"Team {i+1} in {dept.name}",
                    status="active",
                )''',
    '''            team = Team(
                    id=self._create_id("team-"),
                    organization_id=self.context.organization_id,
                    department_id=dept.id,
                    name=f"{dept.name} Team {i+1}",
                    code=f"{dept.code}T{i+1}",
                    description=f"Team {i+1} in {dept.name}",
                )''')

# Fix CompanyDecision creation
content = content.replace(
    '''            decision = CompanyDecision(
                id=self._create_id("dec-"),
                organization_id=self.context.organization_id,
                title=f"Decision for {project.name}",
                description=f"Key decision regarding {project.name}",
                status="decided",
                decision_type="strategic",
                proposed_by=self.context.caller.employee_id,
                decided_at=self._now(),
            )''',
    '''            decision = CompanyDecision(
                id=self._create_id("dec-"),
                organization_id=self.context.organization_id,
                decision_id=self._create_id("decd-"),
                kind="strategic",
                title=f"Decision for {project.name}",
                rationale=f"Key decision regarding {project.name}",
                alternatives_json=None,
                impact_label="high",
                expected_improvement=None,
                confidence=0.8,
                owner_label=self.context.caller.employee_id,
                state="decided",
                approver_label=self.context.caller.employee_id,
                note="Test decision",
                approved_at=self._now(),
                scope_type="organization",
                scope_id=self.context.organization_id,
                event_name="test_decision",
                source_event_id=self.context.run_id,
                epistemic_status="confirmed",
                provenance={"test": True},
            )''')

# Fix epistemic_status in SecurityAdapter
content = content.replace(
    'epistemic_status="proposed"',
    'epistemic_status="unknown"'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed multiple issues')