with open('app/services/canonical_fingerprint.py', 'r') as f:
    content = f.read()

# Remove the orphaned except block (lines 411-413)
old = '''        return _compute_fingerprint({
            "table": table_name,
            "organization_id": organization_id,
            "rows": normalized_rows,
        })
        except Exception as e:
            logger.warning(f"Failed to compute fingerprint for table {table_name}: {e}")
            return _compute_fingerprint({"table": table_name, "error": str(e)})

    async def compute_tenant_fingerprint('''

new = '''        return _compute_fingerprint({
            "table": table_name,
            "organization_id": organization_id,
            "rows": normalized_rows,
        })

    async def compute_tenant_fingerprint('''

content = content.replace(old, new)

with open('app/services/canonical_fingerprint.py', 'w') as f:
    f.write(content)
print('Done')