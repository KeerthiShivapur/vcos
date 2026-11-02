import os
os.environ['PATH'] += ';C:\Program Files\PostgreSQL\18\bin'
import subprocess

for ext in ['pg_trgm', '"uuid-ossp"', 'btree_gin', 'btree_gist', 'pgcrypto']:
    result = subprocess.run(['psql', '-U', 'postgres', '-d', 'vcos_test', '-c', f'CREATE EXTENSION IF NOT EXISTS {ext}'], capture_output=True, text=True)
    print(f'{ext}: {result.returncode} - {result.stdout.strip()} - {result.stderr.strip()}')