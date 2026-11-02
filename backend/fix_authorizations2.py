with open('tests/acceptance/test_backup_restore_roundtrip.py', 'r') as f:
    content = f.read()

# Fix the _create_authorizations method - it's adding 'authorizations' (list) instead of 'auth' (the individual authorization)
old = '''            self.db.add(authorizations)
            authorizations.append(authorizations)
        await self.db.flush()
        self.created_entities["authorizations"] = [a.id for a in authorizations]
        return authorizations'''

new = '''            self.db.add(auth)
            authorizations.append(auth)
        await self.db.flush()
        self.created_entities["authorizations"] = [a.id for a in authorizations]
        return authorizations'''

content = content.replace(old, new)

with open('tests/acceptance/test_backup_restore_roundtrip.py', 'w') as f:
    f.write(content)

print('Fixed _create_authorizations')