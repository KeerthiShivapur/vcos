"""Gate 35 — Performance Test Infrastructure.

Benchmarks, load tests, and performance validation for VCOS scale.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    operation: str
    scale: str
    iterations: int
    success_count: int
    error_count: int
    latencies_ms: List[float]
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    stdev_ms: float
    min_ms: float
    max_ms: float
    throughput_ops_sec: float
    started_at: datetime
    completed_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.iterations if self.iterations > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "operation": self.operation,
            "scale": self.scale,
            "iterations": self.iterations,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": self.success_count / self.iterations if self.iterations > 0 else 0,
            "latencies_ms": {
                "p50": self.p50_ms,
                "p90": self.p90_ms,
                "p95": self.p95_ms,
                "p99": self.p99_ms,
                "mean": self.mean_ms,
                "stdev": self.stdev_ms,
                "min": self.min_ms,
                "max": self.max_ms,
            },
            "throughput_ops_sec": self.throughput_ops_sec,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class LoadTestScenario:
    """A load test scenario configuration."""
    name: str
    description: str
    scale: str
    duration_seconds: int
    concurrent_users: int
    operations: List[Dict[str, Any]]
    ramp_up_seconds: int = 30
    ramp_down_seconds: int = 10
    think_time_ms: int = 100
    

class PerformanceTimer:
    """High-resolution timer for measuring operation latency."""
    
    def __init__(self):
        self._start: float = 0
        self._end: float = 0
    
    def start(self) -> None:
        self._start = time.perf_counter()
    
    def stop(self) -> float:
        self._end = time.perf_counter()
        return (self._end - self._start) * 1000  # ms
    
    @property
    def elapsed_ms(self) -> float:
        if self._end > 0:
            return (self._end - self._start) * 1000
        return (time.perf_counter() - self._start) * 1000


class BenchmarkRunner:
    """Runs benchmarks and collects results."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.results: List[BenchmarkResult] = []
    
    async def run_benchmark(
        self,
        name: str,
        operation: Callable,
        scale: str,
        iterations: int = 100,
        warmup: int = 10,
        **kwargs,
    ) -> BenchmarkResult:
        """Run a benchmark with warmup and collect statistics."""
        
        # Warmup
        for _ in range(warmup):
            try:
                await operation(**kwargs)
            except Exception:
                pass
        
        # Actual benchmark
        latencies: List[float] = []
        success_count = 0
        error_count = 0
        
        started_at = utcnow()
        
        for i in range(iterations):
            timer = PerformanceTimer()
            timer.start()
            try:
                await operation(**kwargs)
                timer.stop()
                latencies.append(timer.elapsed_ms)
                success_count += 1
            except Exception as e:
                timer.stop()
                latencies.append(timer.elapsed_ms)
                error_count += 1
        
        completed_at = utcnow()
        
        # Calculate statistics
        if latencies:
            sorted_latencies = sorted(latencies)
            p50 = sorted_latencies[len(sorted_latencies) // 2]
            p90 = sorted_latencies[int(len(sorted_latencies) * 0.9)]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
            mean = statistics.mean(latencies)
            stdev = statistics.stdev(latencies) if len(latencies) > 1 else 0
            min_lat = min(latencies)
            max_lat = max(latencies)
        else:
            p50 = p90 = p95 = p99 = mean = stdev = min_lat = max_lat = 0
        
        duration_sec = (completed_at - started_at).total_seconds()
        throughput = success_count / duration_sec if duration_sec > 0 else 0
        
        result = BenchmarkResult(
            name=name,
            operation=operation.__name__ if hasattr(operation, '__name__') else str(operation),
            scale=scale,
            iterations=iterations,
            success_count=success_count,
            error_count=error_count,
            latencies_ms=latencies,
            p50_ms=p50,
            p90_ms=p90,
            p95_ms=p95,
            p99_ms=p99,
            mean_ms=mean,
            stdev_ms=stdev,
            min_ms=min_lat,
            max_ms=max_lat,
            throughput_ops_sec=throughput,
            started_at=started_at,
            completed_at=completed_at,
            metadata=kwargs.get("metadata", {}),
        )
        
        self.results.append(result)
        return result
    
    async def run_concurrent_benchmark(
        self,
        name: str,
        operation: Callable,
        scale: str,
        concurrency: int,
        total_operations: int,
        **kwargs,
    ) -> BenchmarkResult:
        """Run benchmark with concurrent workers."""
        
        semaphore = asyncio.Semaphore(concurrency)
        latencies: List[float] = []
        errors: List[Exception] = []
        
        async def worker(op_index: int):
            async with semaphore:
                timer = PerformanceTimer()
                timer.start()
                try:
                    await operation(**kwargs)
                    timer.stop()
                    latencies.append(timer.elapsed_ms)
                except Exception as e:
                    timer.stop()
                    latencies.append(timer.elapsed_ms)
                    errors.append(e)
        
        started_at = utcnow()
        
        # Create tasks
        tasks = [worker(i) for i in range(total_operations)]
        await asyncio.gather(*tasks)
        
        completed_at = utcnow()
        
        success_count = total_operations - len(errors)
        error_count = len(errors)
        
        # Calculate statistics
        if latencies:
            sorted_latencies = sorted(latencies)
            p50 = sorted_latencies[len(sorted_latencies) // 2]
            p90 = sorted_latencies[int(len(sorted_latencies) * 0.9)]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
            mean = statistics.mean(latencies)
            stdev = statistics.stdev(latencies) if len(latencies) > 1 else 0
            min_lat = min(latencies)
            max_lat = max(latencies)
        else:
            p50 = p90 = p95 = p99 = mean = stdev = min_lat = max_lat = 0
        
        duration_sec = (completed_at - started_at).total_seconds()
        throughput = success_count / duration_sec if duration_sec > 0 else 0
        
        result = BenchmarkResult(
            name=name,
            operation=operation.__name__ if hasattr(operation, '__name__') else str(operation),
            scale=scale,
            iterations=total_operations,
            success_count=success_count,
            error_count=error_count,
            latencies_ms=latencies,
            p50_ms=p50,
            p90_ms=p90,
            p95_ms=p95,
            p99_ms=p99,
            mean_ms=mean,
            stdev_ms=stdev,
            min_ms=min_lat,
            max_ms=max_lat,
            throughput_ops_sec=throughput,
            started_at=started_at,
            completed_at=completed_at,
            metadata={"concurrency": concurrency, **kwargs.get("metadata", {})},
        )
        
        self.results.append(result)
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all benchmark results."""
        by_scale: Dict[str, List[BenchmarkResult]] = defaultdict(list)
        by_operation: Dict[str, List[BenchmarkResult]] = defaultdict(list)
        
        for r in self.results:
            by_scale[r.scale].append(r)
            by_scale_key = r.operation
            by_operation[r.operation].append(r)
        
        summary = {
            "total_benchmarks": len(self.results),
            "by_scale": {},
            "by_operation": {},
        }
        
        for scale, results in by_scale.items():
            summary["by_scale"][scale] = {
                "count": len(results),
                "avg_p50": statistics.mean([r.p50_ms for r in results]),
                "avg_p95": statistics.mean([r.p95_ms for r in results]),
                "avg_throughput": statistics.mean([r.throughput_ops_sec for r in results]),
                "total_ops": sum(r.iterations for r in results),
            }
        
        for op, results in by_operation.items():
            summary["by_operation"][op] = {
                "count": len(results),
                "avg_p50": statistics.mean([r.p50_ms for r in results]),
                "avg_p95": statistics.mean([r.p95_ms for r in results]),
                "avg_throughput": statistics.mean([r.throughput_ops_sec for r in results]),
            }
        
        return summary
    
    def export_json(self, filepath: str) -> None:
        """Export results to JSON file."""
        data = {
            "generated_at": utcnow().isoformat(),
            "results": [r.to_dict() for r in self.results],
            "summary": self.get_summary(),
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)


class LoadTestRunner:
    """Runs load test scenarios."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.scenario_results: Dict[str, List[BenchmarkResult]] = defaultdict(list)
    
    async def run_scenario(
        self,
        scenario: LoadTestScenario,
        operation_factory: Callable[[str], Callable],
    ) -> Dict[str, Any]:
        """Run a load test scenario."""
        
        runner = BenchmarkRunner(self.db)
        
        # Calculate operations per user
        ops_per_user = sum(op.get("weight", 1) for op in scenario.operations)
        total_ops = scenario.concurrent_users * ops_per_user
        
        # Ramp up
        await self._ramp_up(scenario, operation_factory, runner)
        
        # Steady state
        steady_results = await self._steady_state(scenario, operation_factory, runner)
        
        # Ramp down
        await self._ramp_down(scenario, operation_factory, runner)
        
        return {
            "scenario": scenario.name,
            "scale": scenario.scale,
            "duration_seconds": scenario.duration_seconds,
            "concurrent_users": scenario.concurrent_users,
            "results": [r.to_dict() for r in runner.results],
            "summary": runner.get_summary(),
        }
    
    async def _ramp_up(
        self,
        scenario: LoadTestScenario,
        operation_factory: Callable,
        runner: BenchmarkRunner,
    ) -> None:
        """Gradually increase load."""
        steps = 10
        step_duration = scenario.ramp_up_seconds / steps
        
        for step in range(1, steps + 1):
            concurrency = int(scenario.concurrent_users * step / steps)
            if concurrency == 0:
                continue
            
            tasks = []
            for _ in range(concurrency):
                op_name = self._select_operation(scenario.operations)
                operation = operation_factory(op_name)
                tasks.append(asyncio.create_task(self._run_single_op(operation)))
            
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(step_duration)
    
    async def _steady_state(
        self,
        scenario: LoadTestScenario,
        operation_factory: Callable,
        runner: BenchmarkRunner,
    ) -> List[BenchmarkResult]:
        """Run at steady state load."""
        
        end_time = time.time() + scenario.duration_seconds
        results = []
        
        while time.time() < end_time:
            # Run batch of concurrent operations
            tasks = []
            for _ in range(scenario.concurrent_users):
                op_name = self._select_operation(scenario.operations)
                operation = operation_factory(op_name)
                tasks.append(asyncio.create_task(self._run_single_op(operation)))
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Small think time
            await asyncio.sleep(scenario.think_time_ms / 1000)
        
        return results
    
    async def _ramp_down(
        self,
        scenario: LoadTestScenario,
        operation_factory: Callable,
        runner: BenchmarkRunner,
    ) -> None:
        """Gradually decrease load."""
        steps = 5
        step_duration = scenario.ramp_down_seconds / steps
        
        for step in range(steps, 0, -1):
            concurrency = int(scenario.concurrent_users * step / steps)
            if concurrency == 0:
                continue
            
            tasks = []
            for _ in range(concurrency):
                op_name = self._select_operation(scenario.operations)
                operation = operation_factory(op_name)
                tasks.append(asyncio.create_task(self._run_single_op(operation)))
            
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(step_duration)
    
    def _select_operation(self, operations: List[Dict[str, Any]]) -> str:
        """Select operation based on weights."""
        total_weight = sum(op.get("weight", 1) for op in operations)
        r = random.random() * total_weight
        
        cumulative = 0
        for op in operations:
            cumulative += op.get("weight", 1)
            if r <= cumulative:
                return op["name"]
        
        return operations[0]["name"]
    
    async def _run_single_op(self, operation: Callable) -> float:
        """Run a single operation and return latency."""
        timer = PerformanceTimer()
        timer.start()
        try:
            await operation()
        except Exception:
            pass
        timer.stop()
        return timer.elapsed_ms


class DatabaseAnalyzer:
    """Analyzes database performance characteristics."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def analyze_query_plan(self, query: str, params: Dict = None) -> Dict[str, Any]:
        """Get EXPLAIN ANALYZE for a query."""
        explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
        result = await self.db.execute(text(explain_query), params or {})
        return result.scalar()
    
    async def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """Get table statistics."""
        query = """
        SELECT 
            schemaname,
            relname as table_name,
            n_live_tup as row_count,
            n_dead_tup as dead_tuples,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            last_autoanalyze
        FROM pg_stat_user_tables
        WHERE relname = :table_name
        """
        result = await self.db.execute(text(query), {"table_name": table_name})
        row = result.first()
        return dict(row._mapping) if row else {}
    
    async def get_index_usage(self, table_name: str) -> List[Dict[str, Any]]:
        """Get index usage statistics."""
        query = """
        SELECT 
            indexrelname as index_name,
            idx_scan as scans,
            idx_tup_read as tuples_read,
            idx_tup_fetch as tuples_fetched,
            pg_size_pretty(pg_relation_size(indexrelid)) as index_size
        FROM pg_stat_user_indexes
        WHERE relname = :table_name
        ORDER BY idx_scan DESC
        """
        result = await self.db.execute(text(query), {"table_name": table_name})
        return [dict(row._mapping) for row in result]
    
    async def get_slow_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get slow queries from pg_stat_statements (if available)."""
        try:
            query = """
            SELECT 
                query,
                calls,
                total_exec_time,
                mean_exec_time,
                max_exec_time,
                stddev_exec_time,
                rows
            FROM pg_stat_statements
            ORDER BY mean_exec_time DESC
            LIMIT :limit
            """
            result = await self.db.execute(text(query), {"limit": limit})
            return [dict(row._mapping) for row in result]
        except Exception:
            return []
    
    async def check_missing_indexes(self) -> List[Dict[str, Any]]:
        """Check for missing indexes using pg_stat_user_tables."""
        query = """
        SELECT 
            relname as table_name,
            seq_scan,
            seq_tup_read,
            idx_scan,
            n_live_tup as row_count,
            CASE 
                WHEN seq_scan > 0 AND n_live_tup > 1000 
                THEN 'HIGH: ' || seq_scan || ' sequential scans on ' || n_live_tup || ' rows'
                WHEN seq_scan > 0 AND n_live_tup > 100
                THEN 'MEDIUM: ' || seq_scan || ' sequential scans on ' || n_live_tup || ' rows'
                ELSE 'LOW'
            END as severity
        FROM pg_stat_user_tables
        WHERE seq_scan > idx_scan
        AND n_live_tup > 100
        ORDER BY seq_tup_read DESC
        LIMIT 50
        """
        result = await self.db.execute(text(query))
        return [dict(row._mapping) for row in result]
    
    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        query = """
        SELECT 
            count(*) as total_connections,
            count(*) FILTER (WHERE state = 'active') as active,
            count(*) FILTER (WHERE state = 'idle') as idle,
            count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_tx,
            max(backend_start) as oldest_connection
        FROM pg_stat_activity
        WHERE datname = current_database()
        """
        result = await self.db.execute(text(query))
        row = result.first()
        return dict(row._mapping) if row else {}
    
    async def get_lock_stats(self) -> List[Dict[str, Any]]:
        """Get lock statistics."""
        query = """
        SELECT 
            mode,
            locktype,
            count(*) as count,
            max(granted) as any_granted
        FROM pg_locks
        WHERE database = (SELECT oid FROM pg_database WHERE datname = current_database())
        GROUP BY mode, locktype
        ORDER BY count DESC
        """
        result = await self.db.execute(text(query))
        return [dict(row._mapping) for row in result]


class NPlusOneDetector:
    """Detects N+1 query patterns in code execution."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.query_log: List[Dict[str, Any]] = []
        self._original_execute = None
    
    def start(self) -> None:
        """Start monitoring queries."""
        # This would wrap the database execute method
        # For now, provides interface for manual detection
        self.query_log.clear()
    
    def stop(self) -> List[Dict[str, Any]]:
        """Stop monitoring and return detected N+1 patterns."""
        # Analyze query log for patterns
        patterns = self._analyze_patterns()
        return patterns
    
    def log_query(self, query: str, params: Dict = None, context: str = "") -> None:
        """Log a query for analysis."""
        self.query_log.append({
            "query": query[:500],
            "params": params,
            "context": context,
            "timestamp": utcnow(),
        })
    
    def _analyze_patterns(self) -> List[Dict[str, Any]]:
        """Analyze queries for N+1 patterns."""
        # Group by query pattern (ignoring parameters)
        pattern_counts: Dict[str, int] = defaultdict(int)
        pattern_contexts: Dict[str, List[str]] = defaultdict(list)
        
        for entry in self.query_log:
            # Simplified pattern extraction
            pattern = self._extract_pattern(entry["query"])
            pattern_counts[pattern] += 1
            pattern_contexts[pattern].append(entry["context"])
        
        # Find patterns executed many times
        n_plus_one = []
        for pattern, count in pattern_counts.items():
            if count > 10:  # Threshold
                n_plus_one.append({
                    "pattern": pattern,
                    "count": count,
                    "contexts": pattern_contexts[pattern][:5],
                    "severity": "HIGH" if count > 100 else "MEDIUM" if count > 50 else "LOW",
                })
        
        return sorted(n_plus_one, key=lambda x: x["count"], reverse=True)
    
    def _extract_pattern(self, query: str) -> str:
        """Extract query pattern by removing literals."""
        import re
        # Replace literals with placeholders
        pattern = re.sub(r'\b\d+\b', '?', query)
        pattern = re.sub(r"'[^']*'", "'?'", pattern)
        pattern = re.sub(r'\$\d+', '$?', pattern)
        # Truncate
        return pattern[:200]


# ================================================================
# Predefined Benchmark Operations
# ================================================================

def create_brain_query_operation(company_brain, organization_id: str, user):
    """Create Company Brain query operation for benchmarking."""
    async def operation():
        return await company_brain.answer(
            db=operation.db,
            organization_id=organization_id,
            question="What is the status of Project Alpha?",
            user=user,
        )
    operation.db = None  # Will be set by runner
    return operation


def create_search_operation(search_service, organization_id: str, user_id: str, user):
    """Create search operation for benchmarking."""
    queries = [
        "project alpha",
        "budget Q1",
        "meeting notes",
        "API documentation",
        "security policy",
    ]
    
    async def operation():
        query = random.choice(queries)
        return await search_service.search(
            db=operation.db,
            organization_id=organization_id,
            query=query,
            user_id=user_id,
            user=user,
        )
    operation.db = None
    return operation


def create_context_build_operation(build_context, organization_id: str, user):
    """Create context building operation for benchmarking."""
    queries = [
        "What is the status of Project Alpha?",
        "Who owns the payment service?",
        "Show me recent decisions",
        "What are the risks this quarter?",
    ]
    
    async def operation():
        query = random.choice(queries)
        return await build_context(
            db=operation.db,
            user=user,
            query=query,
            organization_id=organization_id,
        )
    operation.db = None
    return operation


def create_canonical_mutation_operation(canonical_mutation_boundary, organization_id: str, user):
    """Create canonical mutation operation for benchmarking."""
    async def operation():
        return await canonical_mutation_boundary.propose(
            db=operation.db,
            organization_id=organization_id,
            actor_id=user.id,
            proposal_type="action",
            title=f"Benchmark Action {uuid.uuid4().hex[:8]}",
            description="Benchmark mutation",
        )
    operation.db = None
    return operation


def create_observation_operation(observability_service, organization_id: str):
    """Create observation recording operation for benchmarking."""
    async def operation():
        return await observability_service.record_observation(
            db=operation.db,
            context=ObservationContext(
                organization_id=organization_id,
                observation_type="metric",
                source="benchmark",
                severity="info",
                title="Benchmark Observation",
                details_json={"benchmark": True, "value": random.uniform(0, 100)},
            )
        )
    operation.db = None
    return operation


# Need to import ObservationContext
from app.services.observability_service import ObservationContext


# ================================================================
# Scale Test Suite
# ================================================================

class ScaleTestSuite:
    """Complete scale test suite for Gate 35."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.benchmark_runner = BenchmarkRunner(db)
        self.load_test_runner = LoadTestRunner(db)
        self.db_analyzer = DatabaseAnalyzer(db)
        self.n_plus_one_detector = NPlusOneDetector(db)
    
    async def run_full_scale_validation(
        self,
        scales: List[str] = None,
    ) -> Dict[str, Any]:
        """Run complete scale validation across all scales."""
        scales = scales or list(SCALE_LEVELS.keys())
        results = {
            "scales_tested": scales,
            "benchmarks": {},
            "load_tests": {},
            "db_analysis": {},
            "n_plus_one": {},
            "timestamp": utcnow().isoformat(),
        }
        
        for scale in scales:
            print(f"\n=== Testing scale: {scale} ({SCALE_LEVELS[scale]} employees) ===")
            
            # Create org for this scale
            org_id = await self._create_scale_org(scale)
            
            # Generate data
            print(f"Generating data for {scale}...")
            from tests.scale.generators import run_scale_generation
            await run_scale_generation(self.db, org_id, scale)
            
            # Run benchmarks
            print(f"Running benchmarks for {scale}...")
            results["benchmarks"][scale] = await self._run_scale_benchmarks(org_id, scale)
            
            # Run load tests
            print(f"Running load tests for {scale}...")
            results["load_tests"][scale] = await self._run_scale_load_tests(org_id, scale)
            
            # Database analysis
            print(f"Analyzing database for {scale}...")
            results["db_analysis"][scale] = await self._analyze_database()
            
            # N+1 detection
            print(f"Detecting N+1 queries for {scale}...")
            results["n_plus_one"][scale] = await self._detect_n_plus_one(org_id, scale)
        
        return results
    
    async def _create_scale_org(self, scale: str) -> str:
        """Create organization for scale testing."""
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name=f"Scale Test {scale.title()} ({SCALE_LEVELS[scale]} employees)",
            slug=f"scale-test-{scale}-{SCALE_LEVELS[scale]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
            status="active",
        )
        self.db.add(org)
        await self.db.flush()
        return org.id
    
    async def _run_scale_benchmarks(self, org_id: str, scale: str) -> Dict[str, Any]:
        """Run all benchmarks for a scale."""
        # This would run the actual benchmarks
        # For now, return structure
        return {
            "brain_query": {"p50_ms": 0, "p95_ms": 0, "throughput": 0},
            "search": {"p50_ms": 0, "p95_ms": 0, "throughput": 0},
            "context_build": {"p50_ms": 0, "p95_ms": 0, "throughput": 0},
            "canonical_mutation": {"p50_ms": 0, "p95_ms": 0, "throughput": 0},
            "observation": {"p50_ms": 0, "p95_ms": 0, "throughput": 0},
        }
    
    async def _run_scale_load_tests(self, org_id: str, scale: str) -> Dict[str, Any]:
        """Run load tests for a scale."""
        return {}
    
    async def _analyze_database(self) -> Dict[str, Any]:
        """Analyze database performance."""
        return {
            "missing_indexes": await self.db_analyzer.check_missing_indexes(),
            "connection_stats": await self.db_analyzer.get_connection_stats(),
            "lock_stats": await self.db_analyzer.get_lock_stats(),
        }
    
    async def _detect_n_plus_one(self, org_id: str, scale: str) -> List[Dict[str, Any]]:
        """Detect N+1 queries."""
        # Would run actual operations with detector
        return []


# Import SCALE_LEVELS
from tests.scale.generators import SCALE_LEVELS


# ================================================================
# Test Definitions
# ================================================================

GATE35_BENCHMARKS = [
    {
        "name": "brain_query_my_day",
        "description": "Employee 'My Day' query via Company Brain",
        "target_p95_ms": 200,
        "target_throughput": 50,
    },
    {
        "name": "brain_query_team_context",
        "description": "Manager 'Team Context' query via Company Brain",
        "target_p95_ms": 500,
        "target_throughput": 20,
    },
    {
        "name": "brain_query_executive",
        "description": "Executive 'Company Health' query via Company Brain",
        "target_p95_ms": 1000,
        "target_throughput": 10,
    },
    {
        "name": "search_universal",
        "description": "Universal search query",
        "target_p95_ms": 300,
        "target_throughput": 100,
    },
    {
        "name": "context_build",
        "description": "Company Context building for query",
        "target_p95_ms": 150,
        "target_throughput": 50,
    },
    {
        "name": "canonical_mutation_propose",
        "description": "Propose canonical mutation",
        "target_p95_ms": 100,
        "target_throughput": 100,
    },
    {
        "name": "canonical_mutation_commit",
        "description": "Commit canonical mutation",
        "target_p95_ms": 200,
        "target_throughput": 50,
    },
    {
        "name": "observation_record",
        "description": "Record canonical observation",
        "target_p95_ms": 50,
        "target_throughput": 1000,
    },
    {
        "name": "health_dashboard",
        "description": "Get health dashboard",
        "target_p95_ms": 500,
        "target_throughput": 20,
    },
    {
        "name": "continuity_cycle",
        "description": "Company continuity cycle advance",
        "target_p95_ms": 1000,
        "target_throughput": 5,
    },
]

GATE35_LOAD_SCENARIOS = [
    LoadTestScenario(
        name="startup_daily",
        description="5 employee startup daily operations",
        scale="startup",
        duration_seconds=60,
        concurrent_users=5,
        operations=[
            {"name": "brain_query_my_day", "weight": 10},
            {"name": "search_universal", "weight": 5},
            {"name": "canonical_mutation_propose", "weight": 2},
            {"name": "observation_record", "weight": 20},
        ],
    ),
    LoadTestScenario(
        name="small_company_daily",
        description="50 employee small company daily operations",
        scale="small",
        duration_seconds=120,
        concurrent_users=20,
        operations=[
            {"name": "brain_query_my_day", "weight": 10},
            {"name": "brain_query_team_context", "weight": 5},
            {"name": "search_universal", "weight": 8},
            {"name": "canonical_mutation_propose", "weight": 3},
            {"name": "observation_record", "weight": 30},
        ],
    ),
    LoadTestScenario(
        name="medium_company_daily",
        description="500 employee medium company daily operations",
        scale="medium",
        duration_seconds=300,
        concurrent_users=100,
        operations=[
            {"name": "brain_query_my_day", "weight": 10},
            {"name": "brain_query_team_context", "weight": 8},
            {"name": "brain_query_executive", "weight": 1},
            {"name": "search_universal", "weight": 10},
            {"name": "context_build", "weight": 5},
            {"name": "canonical_mutation_propose", "weight": 5},
            {"name": "observation_record", "weight": 50},
        ],
    ),
    LoadTestScenario(
        name="large_company_peak",
        description="5000 employee large company peak load",
        scale="large",
        duration_seconds=600,
        concurrent_users=500,
        operations=[
            {"name": "brain_query_my_day", "weight": 15},
            {"name": "brain_query_team_context", "weight": 10},
            {"name": "brain_query_executive", "weight": 2},
            {"name": "search_universal", "weight": 15},
            {"name": "context_build", "weight": 8},
            {"name": "canonical_mutation_propose", "weight": 8},
            {"name": "canonical_mutation_commit", "weight": 3},
            {"name": "observation_record", "weight": 80},
        ],
    ),
]

# Export
__all__ = [
    "BenchmarkResult",
    "LoadTestScenario",
    "PerformanceTimer",
    "BenchmarkRunner",
    "LoadTestRunner",
    "DatabaseAnalyzer",
    "NPlusOneDetector",
    "ScaleTestSuite",
    "GATE35_BENCHMARKS",
    "GATE35_LOAD_SCENARIOS",
    "create_brain_query_operation",
    "create_search_operation",
    "create_context_build_operation",
    "create_canonical_mutation_operation",
    "create_observation_operation",
]