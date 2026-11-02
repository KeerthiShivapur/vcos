from app.api.v1 import auth
print('Auth module loaded:', len(auth.router.routes), 'routes')
for route in auth.router.routes:
    print(f"  {route.path} - {route.methods}")