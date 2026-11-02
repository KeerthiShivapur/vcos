with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The problematic section has this pattern:
# Incomplete restore correctly rejected on real PostgreSQL") assert "failed" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()
#         
#         logger.info("�o. Incomplete restore correctly rejected on real PostgreSQL")
# 
#     @pytest.mark.asyncio

# Find the exact bytes
idx = content.find('Incomplete restore correctly rejected on real PostgreSQL") assert')
if idx >= 0:
    # Get the context
    start = max(0, idx - 100)
    end = min(len(content), idx + 300)
    with open('problem_context.txt', 'w', encoding='utf-8') as f:
        f.write(content[start:end])
    print('Written to problem_context.txt')
else:
    print('Not found')