with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix CompanyGoal - use metric_unit instead of unit
content = content.replace(
    '''goal = CompanyGoal(
                id=self._create_id("goal-"),
                organization_id=self.context.organization_id,
                title=f"Goal for {commitment.title}",
                description=f"Goal for commitment: {commitment.title}",
                target_value=100.0,
                unit="count",
                status="active",
                owner_label=self.context.caller.employee_id,
                fingerprint=f"{self.context.run_id}-goal-{commitment.id}",
                version=1,
            )''',
    '''goal = CompanyGoal(
                id=self._create_id("goal-"),
                organization_id=self.context.organization_id,
                title=f"Goal for {commitment.title}",
                description=f"Goal for commitment: {commitment.title}",
                kind="outcome",
                status="active",
                priority=1,
                metric_kind="completion_rate",
                metric_unit="percent",
                target_value=100.0,
                current_value=0.0,
                owner_person_id=self.context.caller.employee_id,
                owner_label=self.context.caller.employee_id,
                timeline_label="Q1",
                fingerprint=f"{self.context.run_id}-goal-{commitment.id}",
            )''')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed CompanyGoal')