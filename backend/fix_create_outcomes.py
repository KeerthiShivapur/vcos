with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Add _create_outcomes method to WorkAdapter if missing
if '_create_outcomes' not in content:
    idx = content.find('async def _create_commitments')
    if idx >= 0:
        # Find the end of _create_commitments method
        end_idx = content.find('\n    async def ', content.find('async def _create_commitments', content.find('class WorkAdapter')) + 10)
        if end_idx < 0:
            end_idx = content.find('\nclass ', content.find('class WorkAdapter') + 10)
        if end_idx < 0:
            end_idx = len(content)
        
        new_method = '''
    async def _create_outcomes(self, commitments: List[CompanyCommitment]) -> List[ObjectiveOutcome]:
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
        return outcomes

'''
        # Find the end of _create_commitments method
        idx = content.find('async def _create_commitments')
        if idx >= 0:
            end_idx = content.find('\n    async def ', content.find('async def _create_commitments', content.find('class WorkAdapter')) + 10)
            if end_idx < 0:
                end_idx = content.find('\nclass ', content.find('class WorkAdapter') + 10)
            if end_idx < 0:
                end_idx = len(content)
            
            content = content[:end_idx] + new_method + content[end_idx:]
            print('Added _create_outcomes method')

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed')