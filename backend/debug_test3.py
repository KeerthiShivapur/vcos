import asyncio
import sys
sys.path.insert(0, 'D:/vcos1/workspace/vcos/backend')

async def debug_test():
    from tests.conftest import client, db_session_factory
    from app.intelligence.governed_commitment_engine import governed_commitment_engine
    from tests.conftest import register_org
    
    async for client_fixture in client():
        client_obj = client_fixture
        async for db_session_factory in db_session_factory():
            async with db_session_factory() as session:
                # Register org and user
                reg = await register_org(client_obj, name="Debug Corp", email="debug@test.co")
                org_id = reg["organization"]["id"]
                user_id = reg["user"]["id"]
                
                # Create commitment
                commitment = await governed_commitment_engine.create_commitment(
                    session, org_id, user_id=user_id,
                    commitment_type="unconditional", title="Test",
                    scope_type="company",
                )
                print(f"Created commitment: {commitment.id}, state={commitment.state}")
                
                # Transition to pending_authorization
                print("Calling transition 1: pending_authorization")
                commitment = await governed_commitment_engine.transition_commitment(
                    session, org_id, commitment.id,
                    user_id=user_id,
                    new_state="pending_authorization",
                    reason="Submitted for authorization",
                )
                print(f"After 1st transition: state={commitment.state}")
                
                # Transition to authorized
                print("Calling transition 2: authorized")
                commitment = await governed_commitment_engine.transition_commitment(
                    session, org_id, commitment.id,
                    user_id=user_id,
                    new_state="authorized",
                    reason="Governance approved",
                )
                print(f"After 2nd transition: state={commitment.state}")
                print(f"About to call transition to 'active', commitment.state={commitment.state}")
                
                # Transition to active - THIS SHOULD WORK
                print("Calling transition_commitment with new_state='active'")
                commitment = await governed_commitment_engine.transition_commitment(
                    session, org_id, commitment.id,
                    user_id=user_id,
                    new_state="active",
                    reason="Execution started",
                )
                print(f"After 3rd transition: state={commitment.state}")

asyncio.run(debug_test())
print("Debug test completed")