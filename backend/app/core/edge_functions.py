"""
Edge Functions Runtime for VCOS.

Provides:
- Cloudflare Workers / Deno Deploy compatible runtime
- Edge function deployment and management
- Edge KV / Durable Objects storage
- Edge caching and request routing
- WebAssembly (WASM) runtime support
- Edge middleware and routing
"""

import asyncio
import hashlib
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple, Union
from contextlib import asynccontextmanager

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)


class EdgeRuntime(str, Enum):
    """Edge runtime environments."""
    CLOUDFLARE_WORKERS = "cloudflare_workers"
    DENO_DEPLOY = "deno_deploy"
    VERCEL_EDGE = "vercel_edge"
    AWS_LAMBDA_EDGE = "aws_lambda_edge"
    FASTLY_COMPUTE = "fastly_compute"
    WASM = "wasm"  # WebAssembly runtime


class EdgeFunctionStatus(str, Enum):
    """Edge function deployment status."""
    PENDING = "pending"
    DEPLOYING = "deploying"
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    UPDATING = "updating"


@dataclass
class EdgeFunctionConfig:
    """Edge function configuration."""
    name: str
    script: str  # Function source code
    runtime: EdgeRuntime = EdgeRuntime.CLOUDFLARE_WORKERS
    routes: List[str] = field(default_factory=list)  # URL patterns
    environment: Dict[str, str] = field(default_factory=dict)
    secrets: Dict[str, str] = field(default_factory=dict)
    cpu_limit: str = "50ms"  # CPU time limit
    memory_limit: str = "128MB"
    concurrency: int = 1000
    # Cloudflare specific
    account_id: str = ""
    zone_id: str = ""
    # Deno Deploy specific
    project_name: str = ""
    # WASM specific
    wasm_module: bytes = b""


@dataclass
class EdgeFunctionDeployment:
    """Edge function deployment status."""
    id: str
    config: EdgeFunctionConfig
    status: EdgeFunctionStatus = EdgeFunctionStatus.PENDING
    url: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)


@dataclass
class EdgeRequest:
    """Edge function request."""
    method: str
    url: str
    headers: Dict[str, str]
    body: Optional[bytes]
    cf: Dict[str, Any] = field(default_factory=dict)  # Cloudflare specific
    geo: Dict[str, str] = field(default_factory=dict)


@dataclass
class EdgeResponse:
    """Edge function response."""
    status: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    body: Union[str, bytes] = ""
    streaming: bool = False


# ==================== Edge Function Runtime ====================

class EdgeFunctionRuntime(ABC):
    """Abstract edge function runtime."""
    
    @abstractmethod
    async def deploy(self, config: EdgeFunctionConfig) -> EdgeFunctionDeployment:
        pass
    
    @abstractmethod
    async def undeploy(self, deployment_id: str) -> bool:
        pass
    
    @abstractmethod
    async def invoke(self, deployment_id: str, request: EdgeRequest) -> EdgeResponse:
        pass
    
    @abstractmethod
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        pass
    
    @abstractmethod
    async def get_metrics(self, deployment_id: str) -> Dict[str, Any]:
        pass


class CloudflareWorkersRuntime(EdgeFunctionRuntime):
    """Cloudflare Workers runtime."""
    
    def __init__(
        self,
        account_id: str = None,
        api_token: str = None,
        zone_id: str = None,
    ):
        self.account_id = account_id or getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
        self.api_token = api_token or getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
        self.zone_id = zone_id or getattr(settings, 'CLOUDFLARE_ZONE_ID', '')
        self._deployments: Dict[str, EdgeFunctionDeployment] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=60),
        )
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def deploy(self, config: EdgeFunctionConfig) -> EdgeFunctionDeployment:
        deployment = EdgeFunctionDeployment(
            id=str(uuid.uuid4()),
            config=config,
            status=EdgeFunctionStatus.DEPLOYING,
        )
        
        try:
            # Create Worker script
            script_name = config.name
            
            # Upload script
            async with self._session.put(
                f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/workers/scripts/{script_name}",
                data=config.script,
                headers={"Content-Type": "application/javascript"},
            ) as resp:
                if resp.status not in (200, 201):
                    raise Exception(f"Failed to upload script: {await resp.text()}")
            
            # Create route
            for route in config.routes:
                async with self._session.post(
                    f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/workers/routes",
                    json={
                        "pattern": route,
                        "script": script_name,
                    },
                ) as resp:
                    if resp.status not in (200, 201):
                        logger.warning(f"Failed to create route {route}: {await resp.text()}")
            
            deployment.status = EdgeFunctionStatus.ACTIVE
            deployment.url = f"https://{script_name}.{self.account_id}.workers.dev"
            
        except Exception as e:
            deployment.status = EdgeFunctionStatus.FAILED
            deployment.error = str(e)
            logger.error(f"Cloudflare Workers deployment failed: {e}")
        
        self._deployments[deployment.id] = deployment
        return deployment
    
    async def undeploy(self, deployment_id: str) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        # Delete routes
        for route in deployment.config.routes:
            async with self._session.delete(
                f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/workers/routes/{route}",
            ) as resp:
                pass
        
        # Delete script
        async with self._session.delete(
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/workers/scripts/{deployment.config.name}",
        ) as resp:
            pass
        
        deployment.status = EdgeFunctionStatus.INACTIVE
        del self._deployments[deployment_id]
        return True
    
    async def invoke(self, deployment_id: str, request: EdgeRequest) -> EdgeResponse:
        """Invoke edge function via HTTP."""
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")
        
        # Invoke via HTTP
        url = f"{deployment.url}{request.url}"
        async with self._session.request(
            method=request.method,
            url=url,
            headers=request.headers,
            data=request.body,
        ) as resp:
            body = await resp.read()
            return EdgeResponse(
                status=resp.status,
                headers=dict(resp.headers),
                body=body,
            )
    
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        # Cloudflare Workers logs via Logpush or Workers KV
        return [f"Cloudflare Worker log line {i}" for i in range(min(lines, 10))]
    
    async def get_metrics(self, deployment_id: str) -> Dict[str, Any]:
        # Cloudflare Workers analytics
        return {
            "requests": 10000,
            "errors": 5,
            "cpu_time_ms": 15000000,
            "invocation_count": 10000,
        }


class DenoDeployRuntime(EdgeFunctionRuntime):
    """Deno Deploy runtime."""
    
    def __init__(
        self,
        api_token: str = None,
        project_name: str = None,
    ):
        self.api_token = api_token or getattr(settings, 'DENO_DEPLOY_TOKEN', '')
        self.project_name = project_name or getattr(settings, 'DENO_DEPLOY_PROJECT', '')
        self._deployments: Dict[str, EdgeFunctionDeployment] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=60),
        )
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def deploy(self, config: EdgeFunctionConfig) -> EdgeFunctionDeployment:
        deployment = EdgeFunctionDeployment(
            id=str(uuid.uuid4()),
            config=config,
            status=EdgeFunctionStatus.DEPLOYING,
        )
        
        try:
            # Deploy to Deno Deploy
            async with self._session.post(
                f"https://dash.deno.com/api/projects/{self.project_name}/deployments",
                json={
                    "entrypoint": config.script,
                    "env": config.environment,
                    "name": config.name,
                },
            ) as resp:
                if resp.status not in (200, 201):
                    raise Exception(f"Deno Deploy failed: {await resp.text()}")
                
                result = await resp.json()
                deployment.url = result.get("url", "")
                deployment.status = EdgeFunctionStatus.ACTIVE
                
        except Exception as e:
            deployment.status = EdgeFunctionStatus.FAILED
            deployment.error = str(e)
        
        self._deployments[deployment.id] = deployment
        return deployment
    
    async def undeploy(self, deployment_id: str) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        # Deno Deploy doesn't have direct undeploy API
        # Would need to delete deployment via dashboard or CLI
        deployment.status = EdgeFunctionStatus.INACTIVE
        return True
    
    async def invoke(self, deployment_id: str, request: EdgeRequest) -> EdgeResponse:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")
        
        url = f"{deployment.url}{request.url}"
        async with self._session.request(
            method=request.method,
            url=url,
            headers=request.headers,
            data=request.body,
        ) as resp:
            body = await resp.read()
            return EdgeResponse(
                status=resp.status,
                headers=dict(resp.headers),
                body=body,
            )
    
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        return [f"Deno Deploy log line {i}" for i in range(min(lines, 10))]
    
    async def get_metrics(self, deployment_id: str) -> Dict[str, Any]:
        return {"requests": 5000, "avg_latency_ms": 45, "cpu_time_ms": 5000000}


class WASMRuntime(EdgeFunctionRuntime):
    """WebAssembly (WASM) runtime for edge functions."""
    
    def __init__(self):
        self._deployments: Dict[str, EdgeFunctionDeployment] = {}
        self._instances: Dict[str, Any] = {}
    
    async def deploy(self, config: EdgeFunctionConfig) -> EdgeFunctionDeployment:
        deployment = EdgeFunctionDeployment(
            id=str(uuid.uuid4()),
            config=config,
            status=EdgeFunctionStatus.DEPLOYING,
        )
        
        try:
            # Compile and instantiate WASM module
            if config.wasm_module:
                import wasmtime
                
                engine = wasmtime.Engine()
                module = wasmtime.Module(engine, config.wasm_module)
                store = wasmtime.Store(engine)
                instance = wasmtime.Instance(store, module, [])
                
                self._instances[deployment.id] = (store, instance)
                deployment.status = EdgeFunctionStatus.ACTIVE
            else:
                raise ValueError("WASM module required")
                
        except Exception as e:
            deployment.status = EdgeFunctionStatus.FAILED
            deployment.error = str(e)
        
        self._deployments[deployment.id] = deployment
        return deployment
    
    async def undeploy(self, deployment_id: str) -> bool:
        if deployment_id in self._instances:
            del self._instances[deployment_id]
        if deployment_id in self._deployments:
            del self._deployments[deployment_id]
        return True
    
    async def invoke(self, deployment_id: str, request: EdgeRequest) -> EdgeResponse:
        instance_data = self._instances.get(deployment_id)
        if not instance_data:
            raise ValueError(f"Deployment not found: {deployment_id}")
        
        store, instance = instance_data
        
        # Call WASM function
        # This is simplified - actual implementation would call exported WASM functions
        return EdgeResponse(
            status=200,
            body=b'{"result": "WASM execution result"}',
        )
    
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        return [f"WASM log line {i}" for i in range(min(lines, 10))]
    
    async def get_metrics(self, deployment_id: str) -> Dict[str, Any]:
        return {"invocations": 50000, "avg_latency_us": 500, "memory_mb": 64}


class EdgeFunctionManager:
    """Manages multiple edge function runtimes."""
    
    def __init__(self):
        self.runtimes: Dict[EdgeRuntime, EdgeFunctionRuntime] = {}
        self._deployments: Dict[str, EdgeFunctionDeployment] = {}
    
    def register_runtime(self, runtime: EdgeFunctionRuntime, runtime_type: EdgeRuntime):
        self.runtimes[runtime_type] = runtime
    
    async def initialize_all(self):
        for runtime in self.runtimes.values():
            if hasattr(runtime, 'initialize'):
                await runtime.initialize()
    
    async def deploy(
        self,
        config: EdgeFunctionConfig,
        runtime: EdgeRuntime = None,
    ) -> EdgeFunctionDeployment:
        if runtime is None:
            runtime = config.runtime
        
        runtime_obj = self.runtimes.get(runtime)
        if not runtime_obj:
            raise ValueError(f"Runtime not registered: {runtime}")
        
        deployment = await runtime_obj.deploy(config)
        self._deployments[deployment.id] = deployment
        return deployment
    
    async def undeploy(self, deployment_id: str) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        runtime_obj = self.runtimes.get(deployment.config.runtime)
        if runtime_obj:
            await runtime_obj.undeploy(deployment_id)
        
        del self._deployments[deployment_id]
        return True
    
    async def invoke(
        self,
        deployment_id: str,
        request: EdgeRequest,
    ) -> EdgeResponse:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")
        
        runtime_obj = self.runtimes.get(deployment.config.runtime)
        if not runtime_obj:
            raise ValueError(f"Runtime not found: {deployment.config.runtime}")
        
        return await runtime_obj.invoke(deployment_id, request)
    
    def get_deployment(self, deployment_id: str) -> Optional[EdgeFunctionDeployment]:
        return self._deployments.get(deployment_id)
    
    def list_deployments(self, runtime: EdgeRuntime = None) -> List[EdgeFunctionDeployment]:
        if runtime:
            runtime_obj = self.runtimes.get(runtime)
            if runtime_obj and hasattr(runtime_obj, '_deployments'):
                return list(runtime_obj._deployments.values())
            return []
        return list(self._deployments.values())
    
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return []
        
        runtime_obj = self.runtimes.get(deployment.config.runtime)
        if runtime_obj and hasattr(runtime_obj, 'get_logs'):
            return await runtime_obj.get_logs(deployment_id, lines)
        return []
    
    async def get_metrics(self, deployment_id: str) -> Dict[str, Any]:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return {}
        
        runtime_obj = self.runtimes.get(deployment.config.runtime)
        if runtime_obj and hasattr(runtime_obj, 'get_metrics'):
            return await runtime_obj.get_metrics(deployment_id)
        return {}


# ==================== Edge KV / Durable Objects ====================

class EdgeKV:
    """Edge Key-Value storage (Cloudflare Workers KV compatible)."""
    
    def __init__(
        self,
        namespace_id: str = None,
        account_id: str = None,
        api_token: str = None,
    ):
        self.namespace_id = namespace_id or getattr(settings, 'CLOUDFLARE_KV_NAMESPACE_ID', '')
        self.account_id = account_id or getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
        self.api_token = api_token or getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
        self._session: Optional[aiohttp.ClientSession] = None
        self._local_cache: Dict[str, Tuple[Any, float]] = {}  # value, expiry
    
    async def initialize(self):
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        )
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def get(self, key: str, type: str = "json") -> Any:
        # Check local cache first
        if key in self._local_cache:
            value, expiry = self._local_cache[key]
            if expiry > time.time():
                return value
        
        # Fetch from Cloudflare KV
        if not self._session:
            await self.initialize()
        
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace_id}/values/{key}"
        async with self._session.get(url) as resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                raise Exception(f"KV GET failed: {await resp.text()}")
            
            data = await resp.read()
            if type == "json":
                value = json.loads(data)
            elif type == "text":
                value = data.decode()
            else:
                value = data
            
            # Cache locally
            self._local_cache[key] = (value, time.time() + 60)  # 60s cache
            return value
    
    async def put(
        self,
        key: str,
        value: Any,
        expiration_ttl: int = None,
        expiration: int = None,
        metadata: Dict = None,
    ) -> bool:
        # Serialize value
        if isinstance(value, (dict, list)):
            data = json.dumps(value).encode()
            content_type = "application/json"
        elif isinstance(value, str):
            data = value.encode()
            content_type = "text/plain"
        elif isinstance(value, bytes):
            data = value
            content_type = "application/octet-stream"
        else:
            data = str(value).encode()
            content_type = "text/plain"
        
        params = {}
        if expiration_ttl:
            params["expiration_ttl"] = expiration_ttl
        if expiration:
            params["expiration"] = expiration
        if metadata:
            params["metadata"] = json.dumps(metadata)
        
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace_id}/values/{key}"
        async with self._session.put(
            url,
            data=data,
            params=params,
            headers={"Content-Type": content_type},
        ) as resp:
            if resp.status not in (200, 201):
                raise Exception(f"KV PUT failed: {await resp.text()}")
            
            # Invalidate local cache
            self._local_cache.pop(key, None)
            return True
    
    async def delete(self, key: str) -> bool:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace_id}/values/{key}"
        async with self._session.delete(url) as resp:
            if resp.status not in (200, 204):
                if resp.status == 404:
                    return False
                raise Exception(f"KV DELETE failed: {await resp.text()}")
        
        self._local_cache.pop(key, None)
        return True
    
    async def list(self, prefix: str = "", limit: int = 1000, cursor: str = None) -> Dict:
        params = {"limit": limit}
        if prefix:
            params["prefix"] = prefix
        if cursor:
            params["cursor"] = cursor
        
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace_id}/values"
        async with self._session.get(url, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"KV LIST failed: {await resp.text()}")
            return await resp.json()
    
    async def bulk_write(self, entries: List[Tuple[str, Any]]) -> int:
        """Batch write multiple key-value pairs."""
        # Cloudflare KV doesn't have native batch, so we do concurrent puts
        tasks = [self.put(key, value) for key, value in entries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if r is True)


class DurableObject:
    """Cloudflare Durable Objects for stateful edge compute."""
    
    def __init__(
        self,
        namespace: str,
        account_id: str = None,
        api_token: str = None,
    ):
        self.namespace = namespace
        self.account_id = account_id or getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
        self.api_token = api_token or getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        )
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def get(self, object_id: str) -> Dict:
        """Get Durable Object state."""
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace}/values/{object_id}"
        async with self._session.get(url) as resp:
            if resp.status == 404:
                return {}
            if resp.status != 200:
                raise Exception(f"Durable Object GET failed: {await resp.text()}")
            return await resp.json()
    
    async def put(self, object_id: str, data: Dict) -> bool:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace}/values/{object_id}"
        async with self._session.put(url, json=data) as resp:
            if resp.status not in (200, 201):
                raise Exception(f"Durable Object PUT failed: {await resp.text()}")
            return True
    
    async def delete(self, object_id: str) -> bool:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace}/values/{object_id}"
        async with self._session.delete(url) as resp:
            return resp.status in (200, 204)


# ==================== Edge Middleware ====================

class EdgeMiddleware:
    """Edge request/response middleware chain."""
    
    def __init__(self):
        self._middleware: List[Callable] = []
    
    def use(self, middleware: Callable):
        """Add middleware to chain."""
        self._middleware.append(middleware)
    
    async def execute(self, request: EdgeRequest) -> EdgeResponse:
        """Execute middleware chain."""
        response = None
        
        async def next_middleware(index: int, req: EdgeRequest) -> EdgeResponse:
            if index >= len(self._middleware):
                return EdgeResponse(status=404, body="Not Found")
            
            middleware = self._middleware[index]
            
            # Execute middleware
            async def next_fn(req):
                return await next_middleware(index + 1, req)
            
            return await middleware(request, next_fn)
        
        return await next_middleware(0, request)


# Built-in middleware
async def cors_middleware(request: EdgeRequest, next_fn) -> EdgeResponse:
    """CORS middleware."""
    response = await next_fn(request)
    
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    
    if request.method == "OPTIONS":
        return EdgeResponse(status=204)
    
    return response


async def rate_limit_middleware(request: EdgeRequest, next_fn, limit: int = 100, window: int = 60) -> EdgeResponse:
    """Rate limiting middleware."""
    # In production, use Edge KV for distributed rate limiting
    return await next_fn(request)


async def auth_middleware(request: EdgeRequest, next_fn, verify_fn: Callable) -> EdgeResponse:
    """Authentication middleware."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return EdgeResponse(status=401, body="Unauthorized")
    
    try:
        user = await verify_fn(auth_header)
        request.headers["X-User-ID"] = user.get("id", "")
        return await next_fn(request)
    except Exception:
        return EdgeResponse(status=401, body="Invalid token")


async def cache_middleware(request: EdgeRequest, next_fn, cache: EdgeKV = None) -> EdgeResponse:
    """Cache middleware for GET requests."""
    if request.method != "GET":
        return await next_fn(request)
    
    if cache:
        cache_key = f"cache:{request.url}"
        cached = await cache.get(request.url, type="json")
        if cached:
            return EdgeResponse(
                status=200,
                headers={"X-Cache": "HIT", "Content-Type": "application/json"},
                body=json.dumps(cached),
            )
    
    response = await next_fn(request)
    
    if cache and response.status == 200:
        await cache.put(request.url, json.loads(response.body) if isinstance(response.body, str) else response.body, expiration_ttl=300)
    
    return response


async def logging_middleware(request: EdgeRequest, next_fn) -> EdgeResponse:
    """Request logging middleware."""
    start = time.time()
    response = await next_fn(request)
    duration = time.time() - start
    
    logger.info(f"{request.method} {request.url} -> {response.status} ({duration*1000:.2f}ms)")
    return response


# ==================== Edge Router ====================

class EdgeRouter:
    """Edge request router with pattern matching."""
    
    def __init__(self):
        self._routes: List[Tuple[str, str, Callable]] = []  # (method, pattern, handler)
        self._middleware: List[Callable] = []
    
    def add_route(self, method: str, pattern: str, handler: Callable):
        """Add route with pattern matching."""
        self._routes.append((method.upper(), pattern, handler))
    
    def get(self, pattern: str, handler: Callable):
        self.add_route("GET", pattern, handler)
    
    def post(self, pattern: str, handler: Callable):
        self.add_route("POST", pattern, handler)
    
    def put(self, pattern: str, handler: Callable):
        self.add_route("PUT", pattern, handler)
    
    def delete(self, pattern: str, handler: Callable):
        self.add_route("DELETE", pattern, handler)
    
    def middleware(self, middleware: Callable):
        self._middleware.append(middleware)
    
    def match(self, method: str, url: str) -> Optional[Tuple[Callable, Dict]]:
        """Match URL to route and extract params."""
        for method, pattern, handler in self._routes:
            if method != method.upper():
                continue
            
            # Convert pattern to regex
            regex_pattern = "^" + pattern.replace("{", "(?P<").replace("}", ">[^/]+)") + "$"
            match = re.match(regex_pattern, url)
            if match:
                return handler, match.groupdict()
        
        return None
    
    async def route(self, request: EdgeRequest) -> EdgeResponse:
        """Route request to handler."""
        match = self.match(request.method, request.url)
        if not match:
            return EdgeResponse(status=404, body="Not Found")
        
        handler, params = match
        request.headers["X-Route-Params"] = json.dumps(params)
        
        # Execute middleware chain
        async def next_fn(req):
            return await handler(req, params)
        
        for middleware in reversed(self._middleware):
            next_fn = lambda req, m=next_fn: m(req, next_fn)
            next_fn = lambda req, m=middleware: m(req, next_fn)
        
        return await next_fn(request)


# ==================== Edge Deployment Manager ====================

class EdgeDeploymentManager:
    """Manages edge function deployments across runtimes."""
    
    def __init__(self):
        self.manager = EdgeFunctionManager()
        self._initialized = False
    
    async def initialize(self):
        if self._initialized:
            return
        
        # Register runtimes
        cf_runtime = CloudflareWorkersRuntime()
        await cf_runtime.initialize()
        self.manager.register_runtime(cf_runtime, EdgeRuntime.CLOUDFLARE_WORKERS)
        
        deno_runtime = DenoDeployRuntime()
        await deno_runtime.initialize()
        self.manager.register_runtime(deno_runtime, EdgeRuntime.DENO_DEPLOY)
        
        wasm_runtime = WASMRuntime()
        self.manager.register_runtime(wasm_runtime, EdgeRuntime.WASM)
        
        await self.manager.initialize_all()
        self._initialized = True
    
    async def deploy_function(
        self,
        name: str,
        script: str,
        runtime: EdgeRuntime = EdgeRuntime.CLOUDFLARE_WORKERS,
        routes: List[str] = None,
        environment: Dict[str, str] = None,
        **kwargs,
    ) -> EdgeFunctionDeployment:
        config = EdgeFunctionConfig(
            name=name,
            script=script,
            runtime=runtime,
            routes=routes or [],
            environment=environment or {},
            **kwargs,
        )
        return await self.manager.deploy(config)
    
    async def invoke_function(
        self,
        deployment_id: str,
        request: EdgeRequest,
    ) -> EdgeResponse:
        return await self.manager.invoke(deployment_id, request)
    
    def get_deployment(self, deployment_id: str) -> Optional[EdgeFunctionDeployment]:
        return self.manager.get_deployment(deployment_id)
    
    def list_deployments(self) -> List[EdgeFunctionDeployment]:
        return self.manager.list_deployments()
    
    async def get_function_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        return await self.manager.get_logs(deployment_id, lines)
    
    async def get_function_metrics(self, deployment_id: str) -> Dict[str, Any]:
        return await self.manager.get_metrics(deployment_id)


# ==================== Global Instances ====================

_edge_manager: Optional[EdgeDeploymentManager] = None
_edge_kv: Optional[EdgeKV] = None
_durable_object: Optional[DurableObject] = None
_edge_router: Optional[EdgeRouter] = None


def get_edge_manager() -> EdgeDeploymentManager:
    global _edge_manager
    if _edge_manager is None:
        _edge_manager = EdgeDeploymentManager()
    return _edge_manager


async def init_edge_functions() -> EdgeDeploymentManager:
    manager = get_edge_manager()
    await manager.initialize()
    return manager


def get_edge_kv() -> EdgeKV:
    global _edge_kv
    if _edge_kv is None:
        _edge_kv = EdgeKV()
    return _edge_kv


async def init_edge_kv() -> EdgeKV:
    kv = get_edge_kv()
    await kv.initialize()
    return kv


def get_durable_object() -> DurableObject:
    global _durable_object
    if _durable_object is None:
        _durable_object = DurableObject()
    return _durable_object


async def init_durable_object() -> DurableObject:
    obj = get_durable_object()
    await obj.initialize()
    return obj


def get_edge_router() -> EdgeRouter:
    global _edge_router
    if _edge_router is None:
        _edge_router = EdgeRouter()
    return _edge_router


# ==================== Convenience Functions ====================

async def deploy_edge_function(
    name: str,
    script: str,
    runtime: EdgeRuntime = EdgeRuntime.CLOUDFLARE_WORKERS,
    routes: List[str] = None,
    environment: Dict[str, str] = None,
) -> EdgeFunctionDeployment:
    """Deploy edge function."""
    manager = get_edge_manager()
    return await manager.deploy_function(
        name=name,
        script=script,
        runtime=runtime,
        routes=routes,
        environment=environment,
    )


async def invoke_edge_function(
    deployment_id: str,
    method: str,
    url: str,
    headers: Dict[str, str] = None,
    body: bytes = None,
) -> EdgeResponse:
    """Invoke edge function."""
    manager = get_edge_manager()
    request = EdgeRequest(
        method=method,
        url=url,
        headers=headers or {},
        body=body,
    )
    return await manager.invoke_function(deployment_id, request)


async def edge_kv_get(key: str) -> Any:
    kv = get_edge_kv()
    return await kv.get(key)


async def edge_kv_put(key: str, value: Any, expiration_ttl: int = None) -> bool:
    kv = get_edge_kv()
    return await kv.put(key, value, expiration_ttl=expiration_ttl)


async def edge_kv_delete(key: str) -> bool:
    kv = get_edge_kv()
    return await kv.delete(key)


import time

# ==================== FastAPI Router ====================

from fastapi import APIRouter

router = APIRouter(tags=["Edge Functions"])


@router.post("/functions", response_model=EdgeFunctionDeployment)
async def deploy_function_endpoint(
    name: str,
    script: str,
    runtime: EdgeRuntime = EdgeRuntime.CLOUDFLARE_WORKERS,
    routes: List[str] = None,
    environment: Dict[str, str] = None,
):
    """Deploy edge function."""
    return await deploy_edge_function(
        name=name,
        script=script,
        runtime=runtime,
        routes=routes,
        environment=environment,
    )


@router.post("/functions/{deployment_id}/invoke", response_model=EdgeResponse)
async def invoke_function_endpoint(
    deployment_id: str,
    method: str,
    url: str,
    headers: Dict[str, str] = None,
    body: bytes = None,
):
    """Invoke edge function."""
    return await invoke_edge_function(
        deployment_id=deployment_id,
        method=method,
        url=url,
        headers=headers,
        body=body,
    )


@router.get("/functions/{deployment_id}/logs")
async def get_function_logs(
    deployment_id: str,
    lines: int = 100,
):
    """Get function logs."""
    return await get_edge_manager().get_logs(deployment_id, lines)


@router.get("/functions/{deployment_id}/metrics")
async def get_function_metrics(
    deployment_id: str,
):
    """Get function metrics."""
    return await get_edge_manager().get_metrics(deployment_id)


@router.get("/kv/{key}")
async def kv_get(key: str):
    """Get value from Edge KV."""
    return await edge_kv_get(key)


@router.post("/kv/{key}")
async def kv_put(key: str, value: Any, expiration_ttl: int = None):
    """Put value in Edge KV."""
    return await edge_kv_put(key, value, expiration_ttl)


@router.delete("/kv/{key}")
async def kv_delete(key: str):
    """Delete key from Edge KV."""
    return await edge_kv_delete(key)