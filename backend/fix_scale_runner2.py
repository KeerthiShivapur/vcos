with open(r'D:\vcos1\workspace\vcos\backend\tests\scale\postgres\scale_runner.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove duplicate COMPLETED transition and fix the _phase_cleanup_existing_data method
old = '''        self._state_machine.transition(ScaleRunState.COMPLETED)

    # ================================================================
    # PIPELINE PHASES
    # ================================================================

    self._state_machine.transition(ScaleRunState.COMPLETED)

    async def _phase_cleanup_existing_data(self):
        """Phase 0: Clean up any existing test data for the organization."""
        self._state_machine.advance_phase(ScaleRunPhase.CLEANUP)
        
        try:
            async with self.environment.session() as session:
                # Delete all data for the test organization
                tables = [
                    "company_actions", "company_commitments", "company_authorizations",
                    "company_decisions", "company_decisions", "company_goals",
                    "company_objectives", "company_initiatives", "company_intents",
                    "company_actions", "company_commitments", "company_authorizations",
                    "company_decisions", "company_commitments", "company_authorizations",
                    "company_decisions", "company_commitments", "company_authorizations",
                    "company_goals", "company_objectives", "company_initiatives", "company_intents",
                    "projects", "tasks", "decisions", "documents",
                    "canonical_observations", "security_events",
                    "company_attention", "canonical_operations",
                    "invoices", "vendors", "purchase_orders", "purchase_requests", "expenses",
                    "customers", "conversations", "messages",
                    "canonical_metrics", "metric_observations",
                    "connector_instances", "sync_runs",
                    "company_state_snapshots", "company_insights",
                    "organizational_learning", "learning_evidence",
                    "company_decisions", "company_commitments", "company_authorizations",
                    "company_objectives", "company_goals", "company_actions",
                    "company_state_snapshots", "company_attention",
                    "organizational_learning", "learning_evidence",
                    "canonical_metrics", "metric_observations",
                    "connector_instances", "sync_runs",
                    "company_state_snapshots", "company_attention",
                    "organizational_learning", "learning_evidence",
                    "canonical_metrics", "metric_observations",
                    "connector_instances", "sync_runs",
                    "company_state_snapshots", "company_attention",
                    "organizational_learning", "learning_evidence",
                    "employees", "departments", "teams", "projects", "tasks",
                    "decisions", "documents", "wiki_pages", "policies", "sops",
                    "templates", "conversations", "messages",
                    "canonical_metrics", "metric_observations",
                    "connector_instances", "sync_runs",
                    "company_state_snapshots", "company_attention",
                    "organizational_learning", "learning_evidence",
                    "canonical_observations", "security_events",
                    "canonical_operations", "operation_attempts",
                    "company_decisions", "company_commitments", "company_authorizations",
                    "company_objectives", "company_goals", "company_actions",
                    "company_actions", "company_decisions", "company_commitments",
                    "company_authorizations", "company_decisions", "company_commitments",
                    "company_authorizations", "company_decisions", "company_commitments",
                    "company_authorizations", "company_decisions", "company_commitments",
                    "company_authorizations",
                ]
                
                for table in tables:
                    try:
                        await session.execute(text(f"DELETE FROM {table} WHERE organization_id = :org_id"), {"org_id": self.profile.organization_id if hasattr(self.profile, 'organization_id') else self.org_id})
                    except Exception:
                        pass  # Table might not exist
                        
                print("DEBUG: Cleaned up existing test data", flush=True)
        except Exception as e:
            print(f"DEBUG: Cleanup failed: {e}", flush=True)
            # Don't fail the run if cleanup fails
            
        self._state_machine.transition(ScaleRunState.INITIALIZED)
        """Phase 1: Environment resolution and comprehensive preflight.\"\"\"

new = '''        self._state_machine.transition(ScaleRunState.COMPLETED)

    # ================================================================
    # PIPELINE PHASES
    # ================================================================

    async def _phase_environment_preflight(self):'''

with open(r'D:\vcos1\workspace\vcos\backend\tests\scale\postgres\scale_runner.py', 'w', encoding='utf-8') as f:
    f.write(content.replace(old, new))
print('Fixed')