import asyncio
import asyncpg

async def create_all_enums():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    await conn.execute('SET search_path TO public')
    
    # All enums from all model files
    enums = [
        # autonomy.py
        ('autonomy_risk_class', "'observe_only', 'propose_only', 'auto_execute_reversible', 'auto_execute_within_policy', 'human_approval_required', 'privileged_human_approval', 'prohibited'"),
        ('autonomy_risk_class_eval', "'observe_only', 'propose_only', 'auto_execute_reversible', 'auto_execute_within_policy', 'human_approval_required', 'privileged_human_approval', 'prohibited'"),
        ('autonomy_proposal_type', "'execute_action', 'create_commitment', 'create_decision', 'create_task', 'create_project', 'allocate_resource', 'assign_responsibility', 'modify_policy', 'trigger_external_operation', 'recommend_decision', 'adjust_plan', 'rebalance_capacity', 'trigger_workflow'"),
        ('autonomy_state', "'discovered', 'eligibility_evaluated', 'proposed', 'evidence_validated', 'governance_evaluated', 'authorization_required', 'authorized', 'committed', 'executing', 'executed', 'outcome_observed', 'verified', 'assessed', 'learned', 'rejected', 'cancelled', 'failed', 'blocked', 'superseded'"),
        ('policy_decision', "'allow', 'deny', 'require_approval', 'require_privileged_approval', 'defer', 'block'"),
        ('autonomy_event_type', "'discovered', 'eligibility_evaluated', 'proposed', 'evidence_validated', 'governance_evaluated', 'authorization_required', 'authorized', 'committed', 'executing', 'executed', 'outcome_observed', 'verified', 'assessed', 'learned', 'rejected', 'cancelled', 'failed', 'blocked', 'superseded', 'policy_evaluated', 'evidence_gathered', 'precondition_checked', 'external_operation_started', 'external_operation_completed', 'external_operation_failed', 'outcome_recorded'"),
        
        # continuous_twin.py
        ('twin_sync_state', "'synced', 'pending', 'stale', 'diverged', 'error'"),
        ('drift_severity', "'low', 'medium', 'high', 'critical'"),
        ('calibration_state', "'pending', 'running', 'completed', 'failed'"),
        ('optimization_state', "'idle', 'analyzing', 'applying', 'validating'"),
        ('learning_signal_type', "'pattern', 'anomaly', 'drift', 'improvement', 'regression'"),
        ('attention_priority', "'low', 'normal', 'high', 'critical'"),
        ('drift_type', "'schema', 'data', 'behavior', 'performance'"),
        ('twin_scope_type', "'global', 'organization', 'project', 'team'"),
        
        # observability.py
        ('degradation_severity', "'low', 'medium', 'high', 'critical'"),
        ('degradation_state', "'detected', 'investigating', 'mitigating', 'resolved'"),
        
        # canonical_company_continuity.py
        ('company_loop_phase', "'observe', 'orient', 'decide', 'act', 'learn'"),
        ('operating_health_state', "'healthy', 'degraded', 'critical', 'recovering'"),
        ('continuity_event_type', "'sync', 'drift', 'prediction', 'optimization', 'learning', 'governance'"),
        ('epistemic_state', "'observed', 'inferred', 'predicted', 'counterfactual', 'proposed'"),
        ('company_state_dimension_g30', "'organization', 'people', 'roles', 'responsibilities', 'capacity', 'work', 'projects', 'customers', 'commercial', 'financial', 'resources', 'procurement', 'processes', 'knowledge', 'decisions', 'commitments', 'actions', 'outcomes', 'predictions', 'counterfactuals', 'digital_twin', 'institutional_memory', 'integrations', 'security', 'governance'"),
        ('consistency_check_type', "'schema', 'data', 'referential', 'temporal', 'semantic'"),
        ('compounding_loop_phase', "'observe', 'orient', 'decide', 'act', 'learn'"),
    ]
    
    for name, values in enums:
        try:
            await conn.execute(f'CREATE TYPE public.{name} AS ENUM ({values})')
            print(f'Created public.{name}')
        except asyncpg.exceptions.DuplicateObjectError:
            print(f'public.{name} already exists')
        except Exception as e:
            print(f'Error creating public.{name}: {e}')
    
    await conn.close()

asyncio.run(create_all_enums())