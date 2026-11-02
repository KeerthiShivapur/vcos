import asyncio
import sys
sys.path.insert(0, 'D:/vcos1/workspace/vcos/backend')

async def test_direct():
    from tests.conftest import client, db_session_factory, register_org
    from app.intelligence.governed_commitment_engine import governed_commitment_engine
    
    async for client_fixture in client():
        client_obj = client_fixture
        async for db_session_factory in db_session_factory():
            async with db_session_factory() as session:
                # Register org and user
                reg = await register_org(client, name="Direct Test", email="direct@test.co")
                org_id = reg["organization"]["id"]
                user_id = reg["user"]["id"]
                
                from app.intelligence.governed_commitment_engine import governed_commitment_engine
                commitment = await governed_commitment_engine.create_commitment(
                    session, org_id, user_id=user_id,
                    commitment_type="unconditional", title="Direct Test",
                    scope_type="company",
                )
                print(f"Created commitment: {commitment.id}, state={commitment.state}")
                
                # Test the transition directly
                print("About to call transition_commitment with new_state='active'")
                from app.intelligence.governed_commitment_engine import governed_commitment_engine
                
                # First, get to authorized state
                commitment = await governed_commitment_engine.create_commitment(
                    session, org_id, user_id=user_id,
                    commitment_type="unconditional", title="Test",
                    scope_type="company",
                )
                
                commitment = await governed_commitment_engine.transition_commitment(
                    session, org_id, commitment.id,
                    user_id=user_id,
                    new_state="pending_authorization",
                    reason="Submitted",
                )
                print(f"After 1st: {commitment.state}")
                
                commitment = await governed_commitment_engine.transition_commitment(
                    session, org_id, commitment.id,
                    user_id=user_id,
                    new_state="authorized",
                    reason="Approved",
                )
                print(f"After 2nd: {commitment.state}")
                print(f"Current state before active: {commitment.state}")
                
                # Now try to transition to active
                print("Calling transition_commitment with new_state='active'")
                commitment = await governed_commitment_engine.transition_commitment(
                    session, org_id, commitment.id,
                    user_id=user_id,
                    new_state="active",
                    reason="Test",
                )
                print(f"After active: {commitment.state}")

asyncio.run(main())