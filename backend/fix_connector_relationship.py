with open('app/models/canonical_integration.py', 'r') as f:
    content = f.read()

# Fix ConnectorInstance - add connector relationship
old = '''    # State
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="disconnected", index=True)  # CONNECTOR_STATES
    error: Mapped[Optional[str]] = mapped_column(Text)'''

new = '''    # State
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="disconnected", index=True)  # CONNECTOR_STATES
    error: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    connector: Mapped["Connector"] = relationship("Connector", lazy="selectin")'''

content = content.replace(old, new)

with open('app/models/canonical_integration.py', 'w') as f:
    f.write(content)
print('Fixed')