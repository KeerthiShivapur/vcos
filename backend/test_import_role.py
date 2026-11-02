import sys
print("Python path:")
for p in sys.path:
    print(f"  {p}")

print("\nImporting role module...")
import app.models.role
print("role module imported successfully")

from app.models.role import Role, UserRoleModel, Permission, RolePermission
print(f"Role: {Role}")
print(f"UserRoleModel: {UserRoleModel}")
print(f"Permission: {Permission}")
print(f"RolePermission: {RolePermission}")

# Check Base.metadata
from app.models.base import Base
print(f"\nTables in Base.metadata:")
for t in Base.metadata.tables:
    print(f"  {t}")

print(f"\nRole in metadata: {'roles' in Base.metadata.tables}")
print(f"UserRoleModel in metadata: {'user_roles' in Base.metadata.tables}")