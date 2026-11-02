from app.models import workspace
print('workspace module loaded')
from app.models.workspace import Workspace
print('Workspace class:', Workspace)
print('Table:', Workspace.__table__)

from app.db.database import Base
print('Tables in metadata:', list(Base.metadata.tables.keys()))