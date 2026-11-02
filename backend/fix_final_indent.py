with open('app/services/onboarding_service.py', 'r') as f:
    content = f.read()

# Fix the continue_provisioning method ending
old = '''            return context
        except Exception as e:
            logger.error(f"Provisioning failed for {organization_id}: {e}")
            raise
    
    

    async def get_onboarding_context'''

new = '''            return context
        except Exception as e:
            logger.error(f"Provisioning failed for {organization_id}: {e}")
            raise

    async def get_onboarding_context'''

content = content.replace(old, new)

with open('app/services/onboarding_service.py', 'w') as f:
    f.write(content)
print('Done')