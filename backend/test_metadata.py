from app.db.database import Base
print('Tables in metadata:', list(Base.metadata.tables.keys()))
print('roles in metadata:', 'roles' in Base.metadata.tables)
print('user_roles in metadata:', 'user_roles' in Base.metadata.tables)