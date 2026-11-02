"""
Snowflake Connector for VCOS.

Provides integration with Snowflake for data warehousing and analytics.
"""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
import snowflake.connector
import snowflake.connector.aio

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
)

logger = logging.getLogger(__name__)


class SnowflakeConnector(BaseConnector):
    """Snowflake Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="snowflake",
        display_name="Snowflake",
        description="Cloud data platform for data warehousing and analytics",
        category="data_warehouse",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Snowflake account identifier"},
                "user": {"type": "string", "description": "Username"},
                "password": {"type": "string", "description": "Password"},
                "private_key": {"type": "string", "description": "Private key for key pair authentication (PEM format)"},
                "private_key_passphrase": {"type": "string", "description": "Passphrase for private key"},
                "warehouse": {"type": "string", "description": "Warehouse name"},
                "database": {"type": "string", "description": "Database name"},
                "schema": {"type": "string", "description": "Schema name"},
                "role": {"type": "string", "description": "Role name"},
            },
            "required": ["account", "user"],
        },
        required_scopes=[],
        supported_operations=[
            "execute_query",
            "list_databases",
            "list_schemas",
            "list_tables",
            "list_views",
            "list_stages",
            "list_files",
            "list_pipes",
            "list_tasks",
            "list_streams",
            "list_functions",
            "list_procedures",
            "list_roles",
            "list_users",
            "list_warehouses",
            "describe_table",
            "get_ddl",
            "execute_ddl",
            "copy_into_table",
            "copy_into_location",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=60,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/snowflake.svg",
        documentation_url="https://docs.snowflake.com/en/developer-guide/python-api/python-api.html",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.account = connection_config.get("account")
        self.user = connection_config.get("user")
        self.password = connection_config.get("password")
        self.private_key = connection_config.get("private_key")
        self.private_key_passphrase = connection_config.get("private_key_passphrase")
        self.warehouse = connection_config.get("warehouse")
        self.database = connection_config.get("database")
        self.schema = connection_config.get("schema")
        self.role = connection_config.get("role")
        self._conn = None
        self._async_conn = None

    async def authenticate(self) -> bool:
        """Authenticate with Snowflake."""
        try:
            if self.private_key:
                # Key pair authentication
                import cryptography.hazmat.primitives.serialization as serialization
                private_key = serialization.load_pem_private_key(
                    self.private_key.encode(),
                    password=self.private_key_passphrase.encode() if self.private_key_passphrase else None,
                )
                pkb = private_key.private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
                self._conn = snowflake.connector.connect(
                    user=self.user,
                    account=self.account,
                    private_key=pkb,
                    warehouse=self.warehouse,
                    database=self.database,
                    schema=self.schema,
                    role=self.role,
                )
            else:
                # Username/password authentication
                self._conn = snowflake.connector.connect(
                    user=self.user,
                    password=self.password,
                    account=self.account,
                    warehouse=self.warehouse,
                    database=self.database,
                    schema=self.schema,
                    role=self.role,
                )

            # Create async connection
            self._async_conn = snowflake.connector.aio.connect(
                user=self.user,
                password=self.password if not self.private_key else None,
                account=self.account,
                private_key=self.private_key,
                private_key_passphrase=self.private_key_passphrase,
                warehouse=self.warehouse,
                database=self.database,
                schema=self.schema,
                role=self.role,
            )

            self._authenticated = True
            logger.info("Snowflake authenticated")
            return True
        except Exception as e:
            logger.error(f"Snowflake authentication failed: {e}")
            raise

    async def _get_connection(self):
        """Get async connection."""
        if not self._async_conn:
            await self.authenticate()
        return self._async_conn

    def _execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute query and return results as list of dicts."""
        cursor = self._conn.cursor()
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    async def _execute_query_async(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute query asynchronously and return results as list of dicts."""
        conn = await self._get_connection()
        cursor = await conn.cursor()
        await cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = await cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "execute_query": self._execute_query,
            "list_databases": self._list_databases,
            "list_schemas": self._list_schemas,
            "list_tables": self._list_tables,
            "list_views": self._list_views,
            "list_stages": self._list_stages,
            "list_files": self._list_files,
            "list_pipes": self._list_pipes,
            "list_tasks": self._list_tasks,
            "list_streams": self._list_streams,
            "list_functions": self._list_functions,
            "list_procedures": self._list_procedures,
            "list_roles": self._list_roles,
            "list_users": self._list_users,
            "list_warehouses": self._list_warehouses,
            "describe_table": self._describe_table,
            "get_ddl": self._get_ddl,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _execute_query(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = filters.get("query") if filters else None
        if not query:
            raise ValueError("query required in filters")

        params = filters.get("params", ()) if filters else ()

        results = await self._execute_query_async(query, params)
        for row in results:
            yield {
                "type": "query_result",
                "id": str(hash(str(row))),
                "data": row,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_databases(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        results = await self._execute_query_async("SHOW DATABASES")
        for db in results:
            yield {
                "type": "database",
                "id": db.get("name", ""),
                "data": db,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_schemas(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        if not database:
            raise ValueError("database required in filters")

        query = f"SHOW SCHEMAS IN DATABASE {database}"
        results = await self._execute_query_async(query)
        for schema in results:
            yield {
                "type": "schema",
                "id": schema.get("name", ""),
                "data": schema,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_tables(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not database or not schema:
            raise ValueError("database and schema required in filters")

        query = f"SHOW TABLES IN SCHEMA {database}.{schema}"
        results = await self._execute_query_async(query)
        for table in results:
            yield {
                "type": "table",
                "id": table.get("name", ""),
                "data": table,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_views(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not database or not schema:
            raise ValueError("database and schema required in filters")

        query = f"SHOW VIEWS IN SCHEMA {database}.{schema}"
        results = await self._execute_query_async(query)
        for view in results:
            yield {
                "type": "view",
                "id": view.get("name", ""),
                "data": view,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_stages(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not database or not schema:
            raise ValueError("database and schema required in filters")

        query = f"SHOW STAGES IN SCHEMA {database}.{schema}"
        results = await self._execute_query_async(query)
        for stage in results:
            yield {
                "type": "stage",
                "id": stage.get("name", ""),
                "data": stage,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_files(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        stage = filters.get("stage") if filters else None
        if not stage:
            raise ValueError("stage required in filters")

        query = f"LIST @{stage}"
        results = await self._execute_query_async(query)
        for file in results:
            yield {
                "type": "file",
                "id": file.get("name", ""),
                "data": file,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_pipes(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not database or not schema:
            raise ValueError("database and schema required in filters")

        query = f"SHOW PIPES IN SCHEMA {database}.{schema}"
        results = await self._execute_query_async(query)
        for pipe in results:
            yield {
                "type": "pipe",
                "id": pipe.get("name", ""),
                "data": pipe,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_tasks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not database or not schema:
            raise ValueError("database and schema required in filters")

        query = f"SHOW TASKS IN SCHEMA {database}.{schema}"
        results = await self._execute_query_async(query)
        for task in results:
            yield {
                "type": "task",
                "id": task.get("name", ""),
                "data": task,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_streams(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not database or not schema:
            raise ValueError("database and schema required in filters")

        query = f"SHOW STREAMS IN SCHEMA {database}.{schema}"
        results = await self._execute_query_async(query)
        for stream in results:
            yield {
                "type": "stream",
                "id": stream.get("name", ""),
                "data": stream,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_functions(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not database or not schema:
            raise ValueError("database and schema required in filters")

        query = f"SHOW FUNCTIONS IN SCHEMA {database}.{schema}"
        results = await self._execute_query_async(query)
        for func in results:
            yield {
                "type": "function",
                "id": func.get("name", ""),
                "data": func,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_procedures(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not database or not schema:
            raise ValueError("database and schema required in filters")

        query = f"SHOW PROCEDURES IN SCHEMA {database}.{schema}"
        results = await self._execute_query_async(query)
        for proc in results:
            yield {
                "type": "procedure",
                "id": proc.get("name", ""),
                "data": proc,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_roles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        results = await self._execute_query_async("SHOW ROLES")
        for role in results:
            yield {
                "type": "role",
                "id": role.get("name", ""),
                "data": role,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        results = await self._execute_query_async("SHOW USERS")
        for user in results:
            yield {
                "type": "user",
                "id": user.get("name", ""),
                "data": user,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_warehouses(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        results = await self._execute_query_async("SHOW WAREHOUSES")
        for wh in results:
            yield {
                "type": "warehouse",
                "id": wh.get("name", ""),
                "data": wh,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _describe_table(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        table = filters.get("table") if filters else None
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema
        if not table or not database or not schema:
            raise ValueError("table, database, and schema required in filters")

        query = f"DESCRIBE TABLE {database}.{schema}.{table}"
        results = await self._execute_query_async(query)
        for col in results:
            yield {
                "type": "column",
                "id": col.get("name", ""),
                "data": col,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _get_ddl(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        object_type = filters.get("object_type") if filters else None
        object_name = filters.get("object_name") if filters else None
        database = filters.get("database") if filters else self.database
        schema = filters.get("schema") if filters else self.schema

        if not object_type or not object_name:
            raise ValueError("object_type and object_name required in filters")

        query = f"GET DDL {object_type} {database}.{schema}.{object_name}"
        results = await self._execute_query_async(query)
        for row in results:
            yield {
                "type": "ddl",
                "id": f"{object_type}.{object_name}",
                "data": {"ddl": row.get("text", "")},
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "execute_ddl": self._execute_ddl,
            "copy_into_table": self._copy_into_table,
            "copy_into_location": self._copy_into_location,
        }

        handler = handlers.get(operation)
        if not handler:
            result.success = False
            result.errors.append({"error": f"Unsupported push operation: {operation}"})
            return result

        for item in data:
            try:
                await handler(item)
                result.records_created += 1 if "create" in operation else 0
                result.records_updated += 1 if "update" in operation else 0
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _execute_ddl(self, ddl_data: Dict[str, Any]):
        query = ddl_data.get("query")
        if not query:
            raise ValueError("query required")
        await self._execute_query_async(query)

    async def _copy_into_table(self, copy_data: Dict[str, Any]):
        table = copy_data.get("table")
        stage = copy_data.get("stage")
        pattern = copy_data.get("pattern", ".*")
        file_format = copy_data.get("file_format", "CSV")
        if not table or not stage:
            raise ValueError("table and stage required")

        query = f"COPY INTO {table} FROM @{stage} PATTERN = '{pattern}' FILE_FORMAT = ({file_format})"
        await self._execute_query_async(query)

    async def _copy_into_location(self, copy_data: Dict[str, Any]):
        query = copy_data.get("query")
        stage = copy_data.get("stage")
        file_format = copy_data.get("file_format", "CSV")
        if not query or not stage:
            raise ValueError("query and stage required")

        query = f"COPY INTO @{stage} FROM ({query}) FILE_FORMAT = ({file_format})"
        await self._execute_query_async(query)

    async def test_connection(self) -> bool:
        try:
            results = await self._execute_query_async("SELECT CURRENT_VERSION()")
            return len(results) > 0
        except Exception as e:
            logger.error(f"Snowflake connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(SnowflakeConnector, SnowflakeConnector.CONFIG)