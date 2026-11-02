with open('app/services/external_operation_service.py', 'r') as f:
    content = f.read()

# Add READ to OperationType enum
old = '''class OperationType(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    TRANSITION = "transition"
    COMMENT = "comment"
    ASSIGN = "assign"'''

new = '''class OperationType(Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    TRANSITION = "transition"
    COMMENT = "comment"
    ASSIGN = "assign"'''

content = content.replace(old, new)

with open('app/services/external_operation_service.py', 'w') as f:
    f.write(content)
print('Fixed')