import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
    
    # Check permissions on public schema
    result = await conn.fetch('''
        SELECT nspname, has_schema_privilege(current_user, nspname, 'CREATE') as can_create
        FROM pg_namespace 
        WHERE nspname = 'public'
    ''')
    for row in result:
        print(f'Schema: {row[0]}, Can CREATE: {row[1]}')
    
    # Grant CREATE on public schema to vcos
    try:
        await conn.execute('GRANT CREATE ON SCHEMA public TO vcos')
        print('Granted CREATE on public schema')
    except Exception as e:
        print(f'Grant error: {e}')
    
    # Check current_schema again
    result = await conn.fetchval('SELECT current_schema()')
    print(f'current_schema after grant: {result}')
    
    await conn.close()

asyncio.run(test())