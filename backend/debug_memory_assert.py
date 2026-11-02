import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the memory assertion and add debug logging
old_assert = '''        memory_count = len(memory_events.scalars().all())
        # Only assert if not using mock restore (which doesn't actually restore data)
        main_restore_mock = False
        if 'main_restore_mock' in locals():
            main_restore_mock = main_restore_mock
        if not main_restore_mock:
            assert memory_count > 0, "Living Company Memory should have events after restore"
        logger.info(f"✅ 1. Living Company Memory: {memory_count} timeline events")'''

new_assert = '''        memory_count = len(memory_events.scalars().all())
        # Debug: check main_restore_mock
        print(f"DEBUG MEMORY: main_restore_mock in locals = {'main_restore_mock' in locals()}")
        if 'main_restore_mock' in locals():
            print(f"DEBUG MEMORY: main_restore_mock = {main_restore_mock}")
        main_restore_mock = False
        if 'main_restore_mock' in locals():
            main_restore_mock = main_restore_mock
        if not main_restore_mock:
            assert memory_count > 0, "Living Company Memory should have events after restore"
        logger.info(f"✅ 1. Living Company Memory: {memory_count} timeline events")'''

if old_assert in content:
    content = content.replace(old_assert, new_assert)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging to memory assertion')
else:
    print('Pattern not found')