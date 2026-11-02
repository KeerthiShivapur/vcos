import app.models.role
from app.models.role import Role, UserRoleModel
from app.models.base import Base

print("Tables in Base.metadata:")
for t in Base.metadata.tables:
    print(f"  {t}")

print("\nRole table:", Role.__table__)
print("UserRoleModel table:", UserRoleModel.__table__)

print("\nIn metadata:")
print("  Role:", "roles" in Base.metadata.tables)
print("  UserRoleModel:", "user_roles" in Base.metadata.tables)