import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def setup():
    engine = create_async_engine('postgresql+asyncpg://postgres@localhost:5432/vcos_test', isolation_level='AUTOCOMMIT')
    async with engine.connect() as conn:
        # Add all missing columns for autonomy_proposals
        columns = [
            ("risk_class_evaluated", "VARCHAR(30) DEFAULT 'human_approval_required'"),
            ("policy_decision", "VARCHAR(30)"),
            ("policy_reason", "TEXT"),
            ("eligibility_result", "VARCHAR(20)"),
            ("eligibility_details", "JSONB DEFAULT '{}'"),
            ("eligibility_evaluated_at", "TIMESTAMP WITH TIME ZONE"),
            ("eligibility_evaluated_by", "VARCHAR(32)"),
            ("evidence_items", "JSONB DEFAULT '[]'"),
            ("evidence_confidence", "FLOAT DEFAULT 0.0"),
            ("evidence_validated", "BOOLEAN DEFAULT FALSE"),
            ("evidence_validated_at", "TIMESTAMP WITH TIME ZONE"),
            ("evidence_validated_by", "VARCHAR(32)"),
            ("governance_evaluated", "BOOLEAN DEFAULT FALSE"),
            ("governance_evaluated_at", "TIMESTAMP WITH TIME ZONE"),
            ("governance_evaluated_by", "VARCHAR(32)"),
            ("governance_details", "JSONB DEFAULT '{}'"),
            ("policy_violations", "JSONB DEFAULT '[]'"),
            ("policy_warnings", "JSONB DEFAULT '[]'"),
            ("authorization_required", "BOOLEAN DEFAULT FALSE"),
            ("approval_required", "BOOLEAN DEFAULT FALSE"),
            ("approval_policy_id", "VARCHAR(32)"),
            ("approval_state", "VARCHAR(20)"),
            ("approver_id", "VARCHAR(32)"),
            ("approved_by", "VARCHAR(32)"),
            ("approved_at", "TIMESTAMP WITH TIME ZONE"),
            ("approval_note", "TEXT"),
            ("rejection_reason", "TEXT"),
            ("commitment_id", "VARCHAR(32)"),
            ("committed_at", "TIMESTAMP WITH TIME ZONE"),
            ("committed_by", "VARCHAR(32)"),
            ("execution_id", "VARCHAR(32)"),
            ("execution_state", "VARCHAR(20)"),
            ("execution_started_at", "TIMESTAMP WITH TIME ZONE"),
            ("execution_completed_at", "TIMESTAMP WITH TIME ZONE"),
            ("execution_duration_ms", "INTEGER"),
            ("execution_error", "TEXT"),
            ("execution_retry_count", "INTEGER DEFAULT 0"),
            ("max_retries", "INTEGER DEFAULT 3"),
            ("external_operation_id", "VARCHAR(32)"),
            ("external_connector_id", "VARCHAR(32)"),
            ("external_operation_type", "VARCHAR(60)"),
            ("external_idempotency_key", "VARCHAR(120)"),
            ("external_result", "JSONB DEFAULT '{}'"),
            ("external_error", "TEXT"),
            ("outcome_id", "VARCHAR(32)"),
            ("outcome_type", "VARCHAR(40)"),
            ("outcome_state", "VARCHAR(20)"),
            ("outcome_summary", "TEXT"),
            ("outcome_details", "JSONB DEFAULT '{}'"),
            ("outcome_epistemic_status", "VARCHAR(20)"),
            ("outcome_observed_at", "TIMESTAMP WITH TIME ZONE"),
            ("outcome_observed_by", "VARCHAR(32)"),
            ("verified", "BOOLEAN DEFAULT FALSE"),
            ("verified_by", "VARCHAR(32)"),
            ("verified_at", "TIMESTAMP WITH TIME ZONE"),
            ("verification_note", "TEXT"),
            ("assessed", "BOOLEAN DEFAULT FALSE"),
            ("assessed_by", "VARCHAR(32)"),
            ("assessed_at", "TIMESTAMP WITH TIME ZONE"),
            ("assessment", "TEXT"),
            ("assessment_details", "JSONB DEFAULT '{}'"),
            ("success_score", "FLOAT"),
            ("learned", "BOOLEAN DEFAULT FALSE"),
            ("learned_at", "TIMESTAMP WITH TIME ZONE"),
            ("lesson_fingerprints", "JSONB DEFAULT '[]'"),
            ("pattern_ids", "JSONB DEFAULT '[]'"),
            ("contradiction_ids", "JSONB DEFAULT '[]'"),
            ("supersedes_id", "VARCHAR(32)"),
            ("superseded_by_id", "VARCHAR(32)"),
            ("version", "INTEGER DEFAULT 1"),
            ("epistemic_status", "VARCHAR(20) DEFAULT 'proposed'"),
            ("metadata_json", "JSONB DEFAULT '{}'"),
            ("proposed_at", "TIMESTAMP WITH TIME ZONE"),
            ("authorized_at", "TIMESTAMP WITH TIME ZONE"),
            ("executed_at", "TIMESTAMP WITH TIME ZONE"),
            ("created_by", "VARCHAR(32)"),
            ("updated_by", "VARCHAR(32)"),
        ]
        
        for col_name, col_def in columns:
            await conn.execute(text(f"""
                ALTER TABLE autonomy_proposals 
                ADD COLUMN IF NOT EXISTS {col_name} {col_def}
            """))
            print(f'Added {col_name}')
        
        # Verify risk_class_evaluated exists
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'autonomy_proposals' AND column_name = 'risk_class_evaluated'
        """))
        print('risk_class_evaluated exists:', bool(result.fetchall()))
    
    await engine.dispose()
    print('Autonomy columns fix complete!')

asyncio.run(setup())