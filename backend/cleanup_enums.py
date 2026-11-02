import asyncpg
import asyncio

async def cleanup_enums():
    # Clean up enums in both postgres and vcos_test databases
    for db_name in ['postgres', 'vcos_test']:
        try:
            conn = await asyncpg.connect(f'postgresql://postgres:postgres@localhost:5432/{db_name}')
            # Get all enum types in the database
            enums = await conn.fetch('''
                SELECT t.typname 
                FROM pg_type t 
                JOIN pg_namespace n ON n.oid = t.typnamespace 
                WHERE t.typtype = 'e' AND n.nspname = 'public'
            ''')
            for enum in enums:
                try:
                    await conn.execute(f'DROP TYPE IF EXISTS {enum["typname"]} CASCADE')
                    print(f'Dropped enum: {enum["typname"]} from {db_name}')
                except Exception as e:
                    print(f'Error dropping {enum["typname"]} from {db_name}: {e}')
            await conn.close()
            print(f'Enum cleanup complete for {db_name}')
        except Exception as e:
            print(f'Error connecting to {db_name}: {e}')
    print('Enum cleanup complete')

asyncio.run(cleanup_enums())