with open('app/services/canonical_reality_integrity_service.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Find and fix the _check_optimization_unverified method
old = '''        query = select(OptimizationContext).where(
            OptimizationContext.organization_id == organization_id,
            OptimizationContext.status.in_(["completed", "evaluated"])
        )'''

new = '''        query = select(OptimizationContext).where(
            OptimizationContext.organization_id == organization_id,
            OptimizationContext.status.in_(["ranked", "selected", "executed"])
        )'''

content = content.replace(old, new)

with open('app/services/canonical_reality_integrity_service.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')