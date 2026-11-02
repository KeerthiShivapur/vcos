with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Add more debug output to see the actual SQL
old = b'        update_stmt = (\r\n            update(model)\r\n            .where(model.id == entity_id)\r\n            .where(model.version == expected_version)\r\n            .values(**update_values)\r\n        )'
new = b'        update_stmt = (\r\n            update(model)\r\n            .where(model.id == entity_id)\r\n            .where(model.version == expected_version)\r\n            .values(**update_values)\r\n        )\r\n        # Debug: print compiled SQL\r\n        from sqlalchemy.dialects.postgresql import dialect as pg_dialect\r\n        compiled = update_stmt.compile(dialect=pg_dialect(), compile_kwargs={"literal_binds": True})\r\n        print(f"DEBUG SQL: {compiled}")'

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Added SQL debug output')