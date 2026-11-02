with open('app/services/release_failure_recovery.py', 'r') as f:
    content = f.read()

# Fix duplicate error_message parameter
old = '''        injection = ReleaseFailureInjection(
            release_id=release.id,
            organization_id=release.organization_id,
            failure_type=failure_type,
            failure_point=failure_point,
            error_message=f"INJECTED: {error_message}",
            error_code=error_code,
            exception_type=exception_type or "InjectedReleaseFailure",
            trigger_condition="always",
            trigger_parameters={},
            error_message=f"INJECTED: {error_message}",
            created_by="system",
            test_mode_only=True,
        )'''

new = '''        injection = ReleaseFailureInjection(
            release_id=release.id,
            organization_id=release.organization_id,
            failure_type=failure_type,
            failure_point=failure_point,
            error_message=f"INJECTED: {error_message}",
            error_code=error_code,
            exception_type=exception_type or "InjectedReleaseFailure",
            trigger_condition="always",
            trigger_parameters={},
            created_by="system",
            test_mode_only=True,
        )'''

content = content.replace(old, new)

with open('app/services/release_failure_recovery.py', 'w') as f:
    f.write(content)
print('Done')