import psycopg2

conn = psycopg2.connect('postgresql://vcos:vcos@localhost:5432/vcos_test')
cur = conn.cursor()
cur.execute("""
    SELECT proname FROM pg_proc 
    WHERE proname = 'current_organization_id' AND pronamespace = 'public'::regnamespace
""")
func = cur.fetchone()
print(f'Function exists: {func}')
if func:
    cur.execute('SELECT current_organization_id()')
    val = cur.fetchone()
    print(f'current_organization_id(): {val}')