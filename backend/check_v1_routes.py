from app.api.v1 import router as api_router
print('V1 router loaded:', len(api_router.routes), 'routes')
for route in api_router.routes:
    print(f"  {route.path} - {route.methods}")