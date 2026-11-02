from app.models import role
print('role module loaded')
from app.models.role import Role
print('Role class:', Role)
print('Table:', Role.__table__)

from app.db.database import Base
print('Tables in metadata:', list(Base.metadata.tables.keys()))