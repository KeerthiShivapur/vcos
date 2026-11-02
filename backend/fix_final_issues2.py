with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix Employee joining_date
content = content.replace(
    'start_date=datetime.now(timezone.utc).date(),',
    'joining_date=datetime.now(timezone.utc).date(),'
)

# Fix ObjectiveOutcome - use objective_id instead of commitment_id
# First, need to update the _create_outcomes method to create objectives first
old_outcomes = '''    async def _create_outcomes(self, commitments: List[CompanyCommitment]) -> List[ObjectiveOutcome]:
        """Create outcomes from commitments."""
        outcomes = []
        
        for commitment in commitments:
            outcome = ObjectiveOutcome(
                id=self._create_id("out-"),
                organization_id=self.context.organization_id,
                commitment_id=commitment.id,
                title=f"Outcome for {commitment.title}",
                description=f"Result of: {commitment.title}",
                status="achieved",
                achieved_at=self._now(),
                achieved_by=self.context.caller.employee_id,
                metrics={"completion": 100, "quality": 95},
            )
            self.context.db.add(outcome)
            outcomes.append(outcome)
        
        await self.context.db.flush()
        return outcomes'''

new_outcomes = '''    async def _create_outcomes(self, commitments: List[CompanyCommitment]) -> List[ObjectiveOutcome]:
        """Create outcomes from commitments."""
        outcomes = []
        
        for commitment in commitments:
            # Create an objective first
            objective = CompanyObjective(
                id=self._create_id("obj-"),
                organization_id=self.context.organization_id,
                title=f"Objective for {commitment.title}",
                description=f"Objective linked to commitment: {commitment.title}",
                kind="commitment_outcome",
                status="active",
                owner_label=self.context.caller.employee_id,
            )
            self.context.db.add(objective)
            await self.context.db.flush()
            
            outcome = ObjectiveOutcome(
                id=self._create_id("out-"),
                organization_id=self.context.organization_id,
                objective_id=objective.id,
                title=f"Outcome for {commitment.title}",
                description=f"Result of: {commitment.title}",
                outcome_state="achieved",
                assessment="completed",
                assessment_confidence=1.0,
                source_event_id=self.context.run_id,
                achieved_at=self._now(),
                achieved_by=self.context.caller.employee_id,
            )
            self.context.db.add(outcome)
            outcomes.append(outcome)
        
        await self.context.db.flush()
        return outcomes'''

content = content.replace(old_outcomes, new_outcomes)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed Employee joining_date and ObjectiveOutcome objective_id')