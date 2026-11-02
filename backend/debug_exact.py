with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Write the exact problematic section to a file for analysis
idx = content.find('Incomplete restore correctly rejected on real PostgreSQL")
assert "failed" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()
        
        logger.info("�o. Incomplete restore correctly rejected on real PostgreSQL")

    @pytest.mark.asyncio')
if idx >= 0:
    with open('exact_block.txt', 'w', encoding='utf-8') as f:
        f.write(content[idx:idx+500])
    print('Written to exact_block.txt')
else:
    print('Not found')