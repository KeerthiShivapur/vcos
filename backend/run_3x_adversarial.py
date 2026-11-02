#!/usr/bin/env python
"""Run adversarial tests 3 times consecutively to verify resource lifecycle."""

import subprocess
import sys

def run_test(run_num):
    print(f"=== ADVERSARIAL RUN {run_num} ===")
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/acceptance/test_integration_adversarial.py",
        "-v", "--tb=short"
    ], cwd=r"D:\vcos1\workspace\vcos\backend")
    
    if result.returncode != 0:
        print(f"Run {run_num} FAILED")
        return False
    
    print(f"=== RUN {run_num} PASSED ===")
    return True

def check_connections():
    import asyncio
    import asyncpg
    
    async def check():
        conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/vcos_test')
        r = await conn.fetch('''
            SELECT 
                count(*) as total,
                count(*) filter (where state = 'idle') as idle,
                count(*) filter (where state = 'active') as active,
                count(*) filter (where state = 'idle in transaction') as idle_in_tx
            FROM pg_stat_activity WHERE datname = 'vcos_test'
        ''')
        print(f"Connection stats: {dict(r[0])}")
        await conn.close()
    
    asyncio.run(check())

if __name__ == "__main__":
    for i in range(1, 4):
        if not run_test(i):
            sys.exit(1)
    
    print("\n=== Verifying connection state ===")
    check_connections()
    print("\n=== ALL 3 RUNS PASSED ===")