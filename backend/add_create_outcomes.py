with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Add _create_outcomes method after _create_commitments
old_end = '''        await self.context.db.flush()
        return commitments
    
    
    '''

new_end = '''        await self.context.db.flush()
        return commitments
    
    async def _create_outcomes(self, commitments: List[CompanyCommitment]) -> List[ObjectiveOutcome]:
        """Create outcomes for commitments."""
        from app.models.execution_strategy import CompanyGoal, CompanyObjective, ObjectiveOutcome
        
        outcomes = []
        
        for commitment in commitments[:3]:
            # First create a CompanyGoal
            goal = CompanyGoal(
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
            )
            self.context.db.add(goal)
            await self.context.db.flush()
            
            # Then create CompanyObjective with goal_id
            objective = CompanyObjective(
                id=self._create_id("obj-"),
                organization_id=self.context.organization_id,
                goal_id=goal.id,
                intent_id=None,
                title=f"Objective for {commitment.title}",
                description=f"Objective for commitment: {commitment.title}",
                kind="outcome",
                status="active",
                required_capabilities=[],
                owner_person_id=self.context.caller.employee_id,
                owner_label=self.context.caller.employee_id,
                current_value=0.0,
                target_value=100.0,
                actual_outcome_state="projected",
                measurement_quality="primary",
                fingerprint=f"{self.context.run_id}-obj-{commitment.id}",
                version=1,
            )
            self.context.db.add(objective)
            await self.context.db.flush()
            
            # Create ObjectiveOutcome
            outcome = ObjectiveOutcome(
                id=self._create_id("out-"),
                organization_id=self.context.organization_id,
                objective_id=objective.id,
                metric_kind="completion_rate",
                unit="percent",
                expected_value=100.0,
                actual_value=0.0,
                variance_pct=0.0,
                outcome_state="projected",
                assessment="inconclusive",
                assessment_confidence=0.5,
                source_event_id=f"{self.context.run_id}-outcome-{commitment.id}",
                recorded_at=self._now(),
                supersedes_id=None,
                superseded_by_id=None,
                supersession_reason=None,
                evidence_fingerprints=[],
                supporting_pattern_ids=[],
                supporting_lesson_fingerprints=[],
                contradicting_evidence_fingerprints=[],
                contradicting_pattern_ids=[],
                contradicting_lesson_fingerprints=[],
                contradiction_ids=[],
                fingerprint=f"{self.context.run_id}-outcome-{commitment.id}",
                version=1,
            )
            self.context.db.add(outcome)
            outcomes.append(outcome)
        
        await self.context.db.flush()
        return outcomes
    
    
    '''

content = content.replace(old_end, new_end)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Added _create_outcomes method')