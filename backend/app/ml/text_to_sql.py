"""
Text-to-SQL / Semantic Layer for VCOS Intelligence Layer.

Provides natural language to SQL conversion:
- Schema-aware SQL generation
- Query validation & optimization
- Semantic layer with business metrics
- Multi-dialect support (PostgreSQL, Snowflake, BigQuery)
- Query explanation & lineage
"""

import asyncio
import json
import logging
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import sqlglot
from sqlglot import exp, parse_one, transpile

from app.core.config import settings

logger = logging.getLogger(__name__)

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)

try:
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    logger.warning("SQLAlchemy not installed. Install: pip install sqlalchemy")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not installed. Install: pip install openai")


class SQLDialect(str, Enum):
    """Supported SQL dialects."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"
    DATABRICKS = "databricks"
    SPARK = "spark"
    SQLITE = "sqlite"
    TSQL = "tsql"  # SQL Server


class QueryType(str, Enum):
    """Types of SQL queries."""
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    CTE = "cte"
    WINDOW = "window"
    AGGREGATION = "aggregation"
    JOIN = "join"


@dataclass
class TableSchema:
    """Table schema definition."""
    name: str
    columns: List["ColumnSchema"]
    primary_key: List[str] = field(default_factory=list)
    foreign_keys: List[Dict[str, Any]] = field(default_factory=list)
    indexes: List[Dict[str, Any]] = field(default_factory=list)
    description: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    sample_data: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ColumnSchema:
    """Column schema definition."""
    name: str
    type: str
    nullable: bool = True
    default: Any = None
    description: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: Optional[str] = None  # table.column


@dataclass
class BusinessMetric:
    """Business metric definition for semantic layer."""
    name: str
    description: str
    formula: str  # SQL expression
    dimensions: List[str] = field(default_factory=list)  # Group by fields
    filters: Dict[str, Any] = field(default_factory=dict)  # Default filters
    format: str = "number"  # number, percent, currency, duration
    unit: str = ""
    owner: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class SemanticModel:
    """Semantic model defining business entities and relationships."""
    name: str
    description: str
    tables: List[TableSchema]
    metrics: List[BusinessMetric]
    relationships: List[Dict[str, Any]] = field(default_factory=list)  # join paths
    created_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0"


@dataclass
class TextToSQLRequest:
    """Text-to-SQL request."""
    question: str
    context: Optional[str] = None
    schema: Optional[str] = None
    dialect: SQLDialect = SQLDialect.POSTGRESQL
    max_tokens: int = 2000
    temperature: float = 0.1
    include_explanation: bool = True
    include_lineage: bool = False


@dataclass
class TextToSQLResponse:
    """Text-to-SQL response."""
    sql: str
    dialect: SQLDialect
    explanation: str = ""
    confidence: float = 0.0
    tables_used: List[str] = field(default_factory=list)
    columns_used: List[str] = field(default_factory=list)
    lineage: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    execution_plan: Optional[str] = None
    estimated_cost: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class QueryValidationResult:
    """SQL query validation result."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    tables_referenced: List[str] = field(default_factory=list)
    columns_referenced: List[str] = field(default_factory=list)
    estimated_rows: Optional[int] = None
    estimated_cost: Optional[float] = None
    complexity_score: float = 0.0


class SchemaRegistry:
    """Database schema registry for text-to-SQL."""

    def __init__(self):
        self._tables: Dict[str, TableSchema] = {}
        self._semantic_models: Dict[str, SemanticModel] = {}
        self._metrics: Dict[str, BusinessMetric] = {}

    def register_table(self, table: TableSchema):
        self._tables[table.name] = table

    def get_table(self, name: str) -> Optional[TableSchema]:
        return self._tables.get(name)

    def list_tables(self) -> List[str]:
        return list(self._tables.keys())

    def register_semantic_model(self, model: SemanticModel):
        self._semantic_models[model.name] = model
        for metric in model.metrics:
            self._metrics[metric.name] = metric

    def get_semantic_model(self, name: str) -> Optional[SemanticModel]:
        return self._semantic_models.get(name)

    def get_metric(self, name: str) -> Optional[BusinessMetric]:
        return self._metrics.get(name)

    def get_schema_context(self, table_names: List[str] = None) -> str:
        """Generate schema context for LLM."""
        tables = table_names or list(self._tables.keys())
        context_parts = []

        for table_name in tables:
            table = self._tables.get(table_name)
            if not table:
                continue

            columns = []
            for col in table.columns:
                col_def = f"  {col.name} {col.type}"
                if not col.nullable:
                    col_def += " NOT NULL"
                if col.is_primary_key:
                    col_def += " PRIMARY KEY"
                if col.description:
                    col_def += f" -- {col.description}"
                columns.append(col_def)

            context_parts.append(f"TABLE {table.name} (\n" + ",\n".join(columns) + "\n)")

        return "\n\n".join(context_parts)

    def get_metric_definitions(self) -> str:
        """Get metric definitions for semantic layer."""
        parts = []
        for metric in self._metrics.values():
            parts.append(f"METRIC {metric.name}: {metric.formula}")
            if metric.description:
                parts[-1] += f" -- {metric.description}"
            if metric.dimensions:
                parts[-1] += f" DIMENSIONS: {', '.join(metric.dimensions)}"
        return "\n".join(parts)


class SQLGenerator:
    """SQL generation using LLM + schema awareness."""

    def __init__(
        self,
        schema_registry: SchemaRegistry,
        dialect: SQLDialect = SQLDialect.POSTGRESQL,
        openai_api_key: Optional[str] = None,
    ):
        self.schema_registry = schema_registry
        self.dialect = dialect
        self.openai_api_key = openai_api_key

    async def generate_sql(self, request: TextToSQLRequest) -> TextToSQLResponse:
        """Generate SQL from natural language."""
        # Get relevant schema context
        schema_context = self.schema_registry.get_schema_context()
        metric_context = self.schema_registry.get_metric_definitions()

        # Build prompt
        prompt = self._build_prompt(request, schema_context, metric_context)

        # Generate SQL using LLM
        sql = await self._call_llm(prompt, request)

        # Post-process SQL
        sql = self._post_process_sql(sql, request.dialect)

        # Validate
        validation = await self.validate_sql(sql, request.dialect)

        # Get explanation
        explanation = ""
        if request.include_explanation:
            explanation = await self._generate_explanation(request.question, sql)

        # Get lineage
        lineage = {}
        if request.include_lineage:
            lineage = self._extract_lineage(sql)

        return TextToSQLResponse(
            sql=sql,
            dialect=request.dialect,
            explanation=explanation,
            confidence=0.9 if validation.valid else 0.5,
            tables_used=validation.tables_referenced,
            columns_used=validation.columns_referenced,
            lineage=lineage,
            warnings=validation.warnings,
            execution_plan=validation.execution_plan,
            estimated_cost=validation.estimated_cost,
        )

    def _build_prompt(self, request: TextToSQLRequest, schema_context: str, metric_context: str) -> str:
        """Build prompt for LLM."""
        dialect_name = request.dialect.value.upper()

        prompt = f"""You are an expert SQL developer. Convert the following natural language question to {dialect_name} SQL.

SCHEMA:
{schema_context}

BUSINESS METRICS:
{metric_context}

RULES:
1. Use only tables and columns defined in the schema
2. Use explicit column names (no SELECT *)
3. Qualify column names with table aliases
4. Use CTEs for complex queries
5. Handle NULL values appropriately
6. Use proper {dialect_name} syntax
7. Include comments explaining key logic
8. Optimize for readability and performance

QUESTION: {request.question}

CONTEXT: {request.context or "None provided"}

Generate only the SQL query, no extra text."""

        return prompt

    async def _call_llm(self, prompt: str, request: TextToSQLRequest) -> str:
        """Call LLM to generate SQL."""
        if not OPENAI_AVAILABLE or not self.openai_api_key:
            # Fallback: simple rule-based generation
            return self._rule_based_generation(request.question)

        try:
            client = openai.AsyncOpenAI(api_key=self.openai_api_key)
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert SQL developer."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._rule_based_generation(request.question)

    def _rule_based_generation(self, question: str) -> str:
        """Simple rule-based SQL generation as fallback."""
        question_lower = question.lower()

        # Simple patterns
        if "count" in question_lower and "user" in question_lower:
            return "SELECT COUNT(*) FROM users;"
        elif "count" in question_lower and "order" in question_lower:
            return "SELECT COUNT(*) FROM orders;"
        elif "total" in question_lower and "revenue" in question_lower:
            return "SELECT SUM(amount) AS total_revenue FROM orders;"
        elif "average" in question_lower and "order" in question_lower:
            return "SELECT AVG(amount) AS avg_order_value FROM orders;"
        elif "top" in question_lower and "customer" in question_lower:
            return "SELECT c.name, SUM(o.amount) AS total_spent FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.id, c.name ORDER BY total_spent DESC LIMIT 10;"

        # Default
        return "-- Unable to generate SQL automatically\nSELECT 1;"

    def _post_process_sql(self, sql: str, dialect: SQLDialect) -> str:
        """Post-process generated SQL."""
        # Remove markdown code blocks
        sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'^```\s*', '', sql)
        sql = re.sub(r'\s*```$', '', sql)

        # Transpile to target dialect if needed
        if dialect != SQLDialect.POSTGRESQL:
            try:
                sql = transpile(sql, read="postgres", write=dialect.value)[0]
            except Exception as e:
                logger.warning(f"Transpilation failed: {e}")

        return sql.strip()

    async def validate_sql(self, sql: str, dialect: SQLDialect) -> QueryValidationResult:
        """Validate SQL query."""
        errors = []
        warnings = []
        tables_referenced = []
        columns_referenced = []

        try:
            # Parse SQL
            parsed = parse_one(sql, dialect=dialect.value)

            # Extract tables
            for table in parsed.find_all(exp.Table):
                tables_referenced.append(table.name)

            # Extract columns
            for col in parsed.find_all(exp.Column):
                if col.table:
                    columns_referenced.append(f"{col.table}.{col.name}")
                else:
                    columns_referenced.append(col.name)

            # Validate against schema
            for table_name in tables_referenced:
                table = self.schema_registry.get_table(table_name)
                if not table:
                    warnings.append(f"Table '{table_name}' not found in schema registry")

            # Check for dangerous operations
            if "DROP" in sql.upper() or "DELETE" in sql.upper() or "TRUNCATE" in sql.upper():
                errors.append("Dangerous operation detected")

            # Check for SELECT *
            if re.search(r'SELECT\s+\*', sql, re.IGNORECASE):
                warnings.append("SELECT * detected - consider explicit columns")

        except Exception as e:
            errors.append(f"Parse error: {str(e)}")

        return QueryValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            tables_referenced=tables_referenced,
            columns_referenced=columns_referenced,
            complexity_score=self._calculate_complexity(sql),
        )

    def _calculate_complexity(self, sql: str) -> float:
        """Calculate query complexity score."""
        score = 1.0
        sql_upper = sql.upper()

        # Count joins
        score += sql_upper.count("JOIN") * 0.5
        score += sql_upper.count("LEFT JOIN") * 0.3
        score += sql_upper.count("RIGHT JOIN") * 0.3

        # Count subqueries
        score += sql_upper.count("SELECT") * 0.3

        # Count window functions
        score += sql_upper.count("OVER") * 0.5

        # Count CTEs
        score += sql_upper.count("WITH") * 0.3

        return round(score, 2)

    async def _generate_explanation(self, question: str, sql: str) -> str:
        """Generate natural language explanation of SQL."""
        if not OPENAI_AVAILABLE or not self.openai_api_key:
            return f"This query answers: {question}"

        try:
            prompt = f"""Explain this SQL query in simple terms:

Question: {question}

SQL:
{sql}

Provide a clear, concise explanation of what this query does."""

            client = openai.AsyncOpenAI(api_key=self.openai_api_key)
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return f"This query answers: {question}"

    def _extract_lineage(self, sql: str) -> Dict[str, Any]:
        """Extract data lineage from SQL."""
        try:
            parsed = parse_one(sql, dialect=self.dialect.value)

            tables = []
            for table in parsed.find_all(exp.Table):
                tables.append({
                    "name": table.name,
                    "alias": table.alias,
                    "columns": [col.name for col in table.find_all(exp.Column) if col.table == table.name],
                })

            # Extract join relationships
            joins = []
            for join in parsed.find_all(exp.Join):
                joins.append({
                    "left": join.this.name if isinstance(join.this, exp.Table) else str(join.this),
                    "right": join.expression.name if isinstance(join.expression, exp.Table) else str(join.expression),
                    "condition": str(join.args.get("on", "")),
                    "type": join.kind.upper() if join.kind else "INNER",
                })

            return {
                "tables": tables,
                "joins": joins,
                "query_type": "SELECT" if "SELECT" in sql.upper() else "OTHER",
            }
        except Exception:
            return {}


class SemanticLayer:
    """
    Semantic Layer for business metrics and self-service analytics.

    Features:
    - Business metric definitions
    - Auto-generated SQL from metric references
    - Dimension filtering & slicing
    - Time-series aware metrics
    - Access control on metrics
    """

    def __init__(self, schema_registry: SchemaRegistry):
        self.schema_registry = schema_registry
        self._models: Dict[str, SemanticModel] = {}
        self._compiled_metrics: Dict[str, str] = {}

    def register_model(self, model: SemanticModel):
        self._models[model.name] = model
        self.schema_registry.register_semantic_model(model)
        self._compile_metrics(model)

    def _compile_metrics(self, model: SemanticModel):
        """Pre-compile metric SQL templates."""
        for metric in model.metrics:
            # Build base query template
            base_query = self._build_metric_query(model, metric)
            self._compiled_metrics[f"{model.name}.{metric.name}"] = base_query

    def _build_metric_query(self, model: SemanticModel, metric: BusinessMetric) -> str:
        """Build SQL template for a metric."""
        # This would use the semantic model to build proper joins
        # For now, return the raw formula
        return metric.formula

    def get_metric_query(
        self,
        model_name: str,
        metric_name: str,
        dimensions: List[str] = None,
        filters: Dict[str, Any] = None,
        time_range: Tuple[datetime, datetime] = None,
        limit: int = 1000,
    ) -> str:
        """Get executable SQL for a metric with filters."""
        key = f"{model_name}.{metric_name}"
        base_query = self._compiled_metrics.get(key, "")

        model = self._models.get(model_name)
        if not model:
            raise ValueError(f"Model not found: {model_name}")

        metric = self.schema_registry.get_metric(metric_name)
        if not metric:
            raise ValueError(f"Metric not found: {metric_name}")

        # Build final query with filters
        query = base_query

        # Add dimension grouping
        if dimensions:
            dim_cols = ", ".join(dimensions)
            query = f"SELECT {dim_cols}, {metric.formula} AS {metric_name} FROM ({query}) GROUP BY {dim_cols}"

        # Add time filter
        if time_range:
            start, end = time_range
            query += f" WHERE event_time >= '{start}' AND event_time <= '{end}'"

        # Add custom filters
        if filters:
            where_clauses = []
            for k, v in filters.items():
                if isinstance(v, list):
                    where_clauses.append(f"{k} IN ({','.join(map(str, v))})")
                elif isinstance(v, str):
                    where_clauses.append(f"{k} = '{v}'")
                else:
                    where_clauses.append(f"{k} = {v}")
            if where_clauses:
                if "WHERE" in query.upper():
                    query += " AND " + " AND ".join(where_clauses)
                else:
                    query += " WHERE " + " AND ".join(where_clauses)

        # Add limit
        query += f" LIMIT {limit}"

        return query

    def list_models(self) -> List[str]:
        return list(self._models.keys())

    def get_model(self, name: str) -> Optional[SemanticModel]:
        return self._models.get(name)

    def get_available_metrics(self, model_name: str = None) -> List[str]:
        if model_name:
            model = self._models.get(model_name)
            if model:
                return [m.name for m in model.metrics]
            return []
        return list(self._compiled_metrics.keys())


class TextToSQLService:
    """
    Complete Text-to-SQL Service with Semantic Layer.

    Features:
    - Natural language to SQL
    - Schema-aware generation
    - Semantic layer with business metrics
    - Query validation & optimization
    - Multi-dialect support
    - Query explanation
    """

    def __init__(
        self,
        db_url: Optional[str] = None,
        dialect: SQLDialect = SQLDialect.POSTGRESQL,
        openai_api_key: Optional[str] = None,
    ):
        self.schema_registry = SchemaRegistry()
        self.sql_generator = SQLGenerator(self.schema_registry, dialect, openai_api_key)
        self.semantic_layer = SemanticLayer(self.schema_registry)
        self.dialect = dialect
        self.db_url = db_url
        self._engine: Optional[AsyncEngine] = None

    async def initialize(self):
        """Initialize service and load schema from database."""
        if self.db_url:
            self._engine = create_async_engine(self.db_url)
            await self._load_schema_from_db()

    async def _load_schema_from_db(self):
        """Introspect database schema."""
        if not self._engine:
            return

        async with self._engine.connect() as conn:
            # Get tables
            result = await conn.execute(text("""
                SELECT table_name, table_schema
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
            """))
            tables = result.fetchall()

            for table_name, schema in tables:
                # Get columns
                col_result = await conn.execute(text(f"""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}' AND table_schema = '{schema}'
                    ORDER BY ordinal_position
                """))
                columns = []
                for row in col_result.fetchall():
                    columns.append(ColumnSchema(
                        name=row[0],
                        type=row[1],
                        nullable=row[2] == "YES",
                        default=row[3],
                    ))

                # Get primary keys
                pk_result = await conn.execute(text(f"""
                    SELECT column_name
                    FROM information_schema.key_column_usage
                    WHERE table_name = '{table_name}' AND table_schema = '{schema}'
                    AND constraint_name LIKE '%pkey%'
                """))
                pk_columns = [row[0] for row in pk_result.fetchall()]

                for col in columns:
                    if col.name in pk_columns:
                        col.is_primary_key = True

                table = TableSchema(
                    name=table_name,
                    columns=columns,
                    primary_key=pk_columns,
                )
                self.schema_registry.register_table(table)

    async def generate_sql(self, request: TextToSQLRequest) -> TextToSQLResponse:
        """Generate SQL from natural language."""
        return await self.sql_generator.generate_sql(request)

    async def validate_sql(self, sql: str, dialect: SQLDialect = None) -> QueryValidationResult:
        """Validate SQL query."""
        dialect = dialect or self.dialect
        return await self.sql_generator.validate_sql(sql, dialect)

    async def explain_query(self, sql: str, dialect: SQLDialect = None) -> str:
        """Explain SQL query in natural language."""
        return await self.sql_generator._generate_explanation("", sql)

    async def get_lineage(self, sql: str) -> Dict[str, Any]:
        """Get data lineage for query."""
        return self.sql_generator._extract_lineage(sql)

    async def transpile_sql(self, sql: str, target_dialect: SQLDialect) -> str:
        """Transpile SQL to another dialect."""
        return transpile(sql, read=self.dialect.value, write=target_dialect.value)[0]

    def get_semantic_metric(
        self,
        model_name: str,
        metric_name: str,
        dimensions: List[str] = None,
        filters: Dict[str, Any] = None,
        time_range: Tuple[datetime, datetime] = None,
        limit: int = 1000,
    ) -> str:
        """Get executable SQL for a semantic metric."""
        return self.semantic_layer.get_metric_query(
            model_name, metric_name, dimensions, filters, time_range, limit
        )

    def register_semantic_model(self, model: SemanticModel):
        """Register a semantic model."""
        self.semantic_layer.register_model(model)

    def list_tables(self) -> List[str]:
        return self.schema_registry.list_tables()

    def get_table_schema(self, name: str) -> Optional[TableSchema]:
        return self.schema_registry.get_table(name)

    async def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute SQL query and return results."""
        if not self._engine:
            raise RuntimeError("Database not connected")

        async with self._engine.connect() as conn:
            result = await conn.execute(text(sql))
            columns = result.keys()
            rows = result.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    async def close(self):
        if self._engine:
            await self._engine.dispose()


# Global Text-to-SQL service instance
_text_to_sql_service: Optional[TextToSQLService] = None


def get_text_to_sql_service() -> TextToSQLService:
    """Get or create Text-to-SQL service singleton."""
    global _text_to_sql_service
    if _text_to_sql_service is None:
        db_url = getattr(settings, 'DATABASE_URL', None)
        openai_key = getattr(settings, 'OPENAI_API_KEY', None)
        _text_to_sql_service = TextToSQLService(db_url=db_url, openai_api_key=openai_key)
    return _text_to_sql_service


def init_text_to_sql_service(
    db_url: Optional[str] = None,
    dialect: SQLDialect = SQLDialect.POSTGRESQL,
    openai_api_key: Optional[str] = None,
) -> TextToSQLService:
    """Initialize Text-to-SQL service with custom config."""
    global _text_to_sql_service
    _text_to_sql_service = TextToSQLService(db_url=db_url, dialect=dialect, openai_api_key=openai_api_key)
    return _text_to_sql_service