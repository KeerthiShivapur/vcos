"""
Inference Service for VCOS ML Platform.

Triton/vLLM/TGI compatible inference service with:
- Multiple backend support (Triton, vLLM, TGI, local)
- Model loading & management
- Batch inference
- Streaming inference
- Request batching & queueing
- Health monitoring
"""

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

import aiohttp

from app.core.config import settings
from app.ml.model_registry import ModelRegistry, ModelVersion, ModelStage, get_model_registry

logger = logging.getLogger(__name__)


class InferenceBackend(str, Enum):
    """Supported inference backends."""
    TRITON = "triton"
    VLLM = "vllm"
    TGI = "tgi"
    LOCAL = "local"
    TORCHSCRIPT = "torchscript"
    ONNX = "onnx"


class InferenceStatus(str, Enum):
    """Inference request status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class InferenceRequest:
    """Inference request."""
    id: str = field(default_factory=lambda: str(uuid4()))
    model_name: str = ""
    model_version: Optional[int] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    stream: bool = False
    request_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    timeout: float = 30.0


@dataclass
class InferenceResponse:
    """Inference response."""
    id: str
    request_id: str
    model_name: str
    model_version: int
    outputs: Dict[str, Any]
    status: InferenceStatus
    latency_ms: float
    tokens_used: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ModelInstance:
    """Running model instance."""
    id: str
    model_name: str
    model_version: int
    backend: InferenceBackend
    endpoint: str
    status: str  # loading, ready, error
    loaded_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class InferenceBackendBase(ABC):
    """Abstract inference backend."""

    def __init__(self, endpoint: str, model_name: str, model_version: int):
        self.endpoint = endpoint
        self.model_name = model_name
        self.model_version = model_version
        self._session: Optional[aiohttp.ClientSession] = None
        self._ready = False

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize backend connection and load model."""
        pass

    @abstractmethod
    async def close(self):
        """Close backend connection."""
        pass

    @abstractmethod
    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        """Run inference."""
        pass

    @abstractmethod
    async def stream_infer(self, request: InferenceRequest) -> AsyncGenerator[InferenceResponse, None]:
        """Stream inference."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check backend health."""
        pass

    @property
    def ready(self) -> bool:
        return self._ready


class TritonBackend(InferenceBackendBase):
    """NVIDIA Triton Inference Server backend."""

    def __init__(self, endpoint: str, model_name: str, model_version: int):
        super().__init__(endpoint, model_name, model_version)
        self.model_repository = f"{endpoint}/v2/models/{model_name}/versions/{model_version}"

    async def initialize(self) -> bool:
        try:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            # Check if model is ready
            async with self._session.get(f"{self.endpoint}/v2/health/ready") as resp:
                if resp.status == 200:
                    self._ready = True
                    logger.info(f"Triton backend ready: {self.endpoint}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Triton initialization failed: {e}")
            return False

    async def close(self):
        if self._session:
            await self._session.close()

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        start = time.time()
        try:
            # Prepare Triton input format
            inputs = []
            for name, data in request.inputs.items():
                inputs.append({
                    "name": name,
                    "shape": data.get("shape", [1]),
                    "datatype": data.get("datatype", "FP32"),
                    "data": data.get("data", []),
                })

            payload = {
                "inputs": inputs,
                "outputs": [{"name": name} for name in request.parameters.get("outputs", ["output"])],
            }

            async with self._session.post(
                f"{self.endpoint}/v2/models/{self.model_name}/versions/{self.model_version}/infer",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=request.timeout),
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return InferenceResponse(
                        id=str(uuid4()),
                        request_id=request.request_id,
                        model_name=self.model_name,
                        model_version=self.model_version,
                        outputs={},
                        status=InferenceStatus.FAILED,
                        latency_ms=(time.time() - start) * 1000,
                        error=error,
                    )

                result = await resp.json()
                outputs = {}
                for output in result.get("outputs", []):
                    outputs[output["name"]] = output["data"]

                return InferenceResponse(
                    id=str(uuid4()),
                    request_id=request.request_id,
                    model_name=self.model_name,
                    model_version=self.model_version,
                    outputs=outputs,
                    status=InferenceStatus.COMPLETED,
                    latency_ms=(time.time() - start) * 1000,
                )
        except Exception as e:
            return InferenceResponse(
                id=str(uuid4()),
                request_id=request.request_id,
                model_name=self.model_name,
                model_version=self.model_version,
                outputs={},
                status=InferenceStatus.FAILED,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    async def stream_infer(self, request: InferenceRequest) -> AsyncGenerator[InferenceResponse, None]:
        # Triton doesn't natively support streaming, yield single response
        yield await self.infer(request)

    async def health_check(self) -> bool:
        try:
            async with self._session.get(f"{self.endpoint}/v2/health/ready") as resp:
                return resp.status == 200
        except Exception:
            return False


class VLLMBackend(InferenceBackendBase):
    """vLLM OpenAI-compatible backend."""

    def __init__(self, endpoint: str, model_name: str, model_version: int):
        super().__init__(endpoint, model_name, model_version)
        self.api_base = f"{endpoint}/v1"

    async def initialize(self) -> bool:
        try:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60)
            )
            # Check model availability
            async with self._session.get(f"{self.api_base}/models") as resp:
                if resp.status == 200:
                    models = await resp.json()
                    model_ids = [m["id"] for m in models.get("data", [])]
                    if self.model_name in model_ids or f"{self.model_name}:{self.model_version}" in model_ids:
                        self._ready = True
                        logger.info(f"vLLM backend ready: {self.endpoint}")
                        return True
            return False
        except Exception as e:
            logger.error(f"vLLM initialization failed: {e}")
            return False

    async def close(self):
        if self._session:
            await self._session.close()

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        start = time.time()
        try:
            # Convert to OpenAI format
            messages = request.inputs.get("messages", [])
            if not messages and "prompt" in request.inputs:
                messages = [{"role": "user", "content": request.inputs["prompt"]}]

            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": request.parameters.get("temperature", 0.7),
                "max_tokens": request.parameters.get("max_tokens", 1024),
                "top_p": request.parameters.get("top_p", 1.0),
                "stream": False,
            }

            async with self._session.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=request.timeout),
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return InferenceResponse(
                        id=str(uuid4()),
                        request_id=request.request_id,
                        model_name=self.model_name,
                        model_version=self.model_version,
                        outputs={},
                        status=InferenceStatus.FAILED,
                        latency_ms=(time.time() - start) * 1000,
                        error=error,
                    )

                result = await resp.json()
                choice = result["choices"][0]
                outputs = {
                    "text": choice["message"]["content"],
                    "finish_reason": choice["finish_reason"],
                }

                usage = result.get("usage", {})
                tokens = usage.get("total_tokens")

                return InferenceResponse(
                    id=str(uuid4()),
                    request_id=request.request_id,
                    model_name=self.model_name,
                    model_version=self.model_version,
                    outputs=outputs,
                    status=InferenceStatus.COMPLETED,
                    latency_ms=(time.time() - start) * 1000,
                    tokens_used=tokens,
                )
        except Exception as e:
            return InferenceResponse(
                id=str(uuid4()),
                request_id=request.request_id,
                model_name=self.model_name,
                model_version=self.model_version,
                outputs={},
                status=InferenceStatus.FAILED,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    async def stream_infer(self, request: InferenceRequest) -> AsyncGenerator[InferenceResponse, None]:
        start = time.time()
        try:
            messages = request.inputs.get("messages", [])
            if not messages and "prompt" in request.inputs:
                messages = [{"role": "user", "content": request.inputs["prompt"]}]

            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": request.parameters.get("temperature", 0.7),
                "max_tokens": request.parameters.get("max_tokens", 1024),
                "top_p": request.parameters.get("top_p", 1.0),
                "stream": True,
            }

            async with self._session.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=request.timeout),
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    yield InferenceResponse(
                        id=str(uuid4()),
                        request_id=request.request_id,
                        model_name=self.model_name,
                        model_version=self.model_version,
                        outputs={},
                        status=InferenceStatus.FAILED,
                        latency_ms=(time.time() - start) * 1000,
                        error=error,
                    )
                    return

                async for line in resp.content:
                    line = line.decode().strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if data.get("choices"):
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield InferenceResponse(
                                    id=str(uuid4()),
                                    request_id=request.request_id,
                                    model_name=self.model_name,
                                    model_version=self.model_version,
                                    outputs={"text": delta["content"], "stream": True},
                                    status=InferenceStatus.RUNNING,
                                    latency_ms=(time.time() - start) * 1000,
                                )
        except Exception as e:
            yield InferenceResponse(
                id=str(uuid4()),
                request_id=request.request_id,
                model_name=self.model_name,
                model_version=self.model_version,
                outputs={},
                status=InferenceStatus.FAILED,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    async def health_check(self) -> bool:
        try:
            async with self._session.get(f"{self.api_base}/models") as resp:
                return resp.status == 200
        except Exception:
            return False


class TGIBackend(InferenceBackendBase):
    """Text Generation Inference (TGI) backend."""

    def __init__(self, endpoint: str, model_name: str, model_version: int):
        super().__init__(endpoint, model_name, model_version)
        self.api_base = endpoint

    async def initialize(self) -> bool:
        try:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60)
            )
            async with self._session.get(f"{self.api_base}/health") as resp:
                if resp.status == 200:
                    self._ready = True
                    logger.info(f"TGI backend ready: {self.endpoint}")
                    return True
            return False
        except Exception as e:
            logger.error(f"TGI initialization failed: {e}")
            return False

    async def close(self):
        if self._session:
            await self._session.close()

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        start = time.time()
        try:
            payload = {
                "inputs": request.inputs.get("prompt", request.inputs.get("text", "")),
                "parameters": {
                    "temperature": request.parameters.get("temperature", 0.7),
                    "max_new_tokens": request.parameters.get("max_tokens", 1024),
                    "top_p": request.parameters.get("top_p", 1.0),
                    "do_sample": True,
                    "return_full_text": False,
                },
            }

            async with self._session.post(
                f"{self.api_base}/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=request.timeout),
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return InferenceResponse(
                        id=str(uuid4()),
                        request_id=request.request_id,
                        model_name=self.model_name,
                        model_version=self.model_version,
                        outputs={},
                        status=InferenceStatus.FAILED,
                        latency_ms=(time.time() - start) * 1000,
                        error=error,
                    )

                result = await resp.json()
                outputs = {
                    "text": result.get("generated_text", ""),
                    "details": result.get("details", {}),
                }

                return InferenceResponse(
                    id=str(uuid4()),
                    request_id=request.request_id,
                    model_name=self.model_name,
                    model_version=self.model_version,
                    outputs=outputs,
                    status=InferenceStatus.COMPLETED,
                    latency_ms=(time.time() - start) * 1000,
                    tokens_used=result.get("details", {}).get("generated_tokens"),
                )
        except Exception as e:
            return InferenceResponse(
                id=str(uuid4()),
                request_id=request.request_id,
                model_name=self.model_name,
                model_version=self.model_version,
                outputs={},
                status=InferenceStatus.FAILED,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    async def stream_infer(self, request: InferenceRequest) -> AsyncGenerator[InferenceResponse, None]:
        start = time.time()
        try:
            payload = {
                "inputs": request.inputs.get("prompt", request.inputs.get("text", "")),
                "parameters": {
                    "temperature": request.parameters.get("temperature", 0.7),
                    "max_new_tokens": request.parameters.get("max_tokens", 1024),
                    "top_p": request.parameters.get("top_p", 1.0),
                    "do_sample": True,
                    "return_full_text": False,
                },
                "stream": True,
            }

            async with self._session.post(
                f"{self.api_base}/generate_stream",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=request.timeout),
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    yield InferenceResponse(
                        id=str(uuid4()),
                        request_id=request.request_id,
                        model_name=self.model_name,
                        model_version=self.model_version,
                        outputs={},
                        status=InferenceStatus.FAILED,
                        latency_ms=(time.time() - start) * 1000,
                        error=error,
                    )
                    return

                async for line in resp.content:
                    line = line.decode().strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "token" in data:
                            yield InferenceResponse(
                                id=str(uuid4()),
                                request_id=request.request_id,
                                model_name=self.model_name,
                                model_version=self.model_version,
                                outputs={"text": data["token"]["text"], "stream": True},
                                status=InferenceStatus.RUNNING,
                                latency_ms=(time.time() - start) * 1000,
                            )
        except Exception as e:
            yield InferenceResponse(
                id=str(uuid4()),
                request_id=request.request_id,
                model_name=self.model_name,
                model_version=self.model_version,
                outputs={},
                status=InferenceStatus.FAILED,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    async def health_check(self) -> bool:
        try:
            async with self._session.get(f"{self.api_base}/health") as resp:
                return resp.status == 200
        except Exception:
            return False


class LocalBackend(InferenceBackendBase):
    """Local Python model backend (PyTorch/ONNX)."""

    def __init__(self, model_name: str, model_version: int, model_path: str = ""):
        super().__init__("local", model_name, model_version)
        self.model_path = model_path
        self._model = None
        self._tokenizer = None

    async def initialize(self) -> bool:
        try:
            # Try to load model
            if self.model_path and self.model_path.endswith(".onnx"):
                import onnxruntime as ort
                self._model = ort.InferenceSession(self.model_path)
            else:
                # Try PyTorch
                import torch
                self._model = torch.jit.load(self.model_path) if self.model_path.endswith(".pt") else None

            if self._model:
                self._ready = True
                logger.info(f"Local backend ready: {self.model_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Local backend initialization failed: {e}")
            return False

    async def close(self):
        self._model = None

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        start = time.time()
        try:
            if not self._model:
                raise Exception("Model not loaded")

            # Run inference
            inputs = request.inputs
            if hasattr(self._model, "run"):  # ONNX Runtime
                output = self._model.run(None, inputs)
                outputs = {"output": output[0].tolist() if hasattr(output[0], "tolist") else output[0]}
            else:  # PyTorch
                import torch
                with torch.no_grad():
                    input_tensor = {k: torch.tensor(v) for k, v in inputs.items()}
                    output = self._model(**input_tensor)
                    outputs = {"output": output.tolist() if hasattr(output, "tolist") else output}

            return InferenceResponse(
                id=str(uuid4()),
                request_id=request.request_id,
                model_name=self.model_name,
                model_version=self.model_version,
                outputs=outputs,
                status=InferenceStatus.COMPLETED,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return InferenceResponse(
                id=str(uuid4()),
                request_id=request.request_id,
                model_name=self.model_name,
                model_version=self.model_version,
                outputs={},
                status=InferenceStatus.FAILED,
                latency_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    async def stream_infer(self, request: InferenceRequest) -> AsyncGenerator[InferenceResponse, None]:
        yield await self.infer(request)

    async def health_check(self) -> bool:
        return self._model is not None


class InferenceService:
    """
    Unified Inference Service.

    Features:
    - Multiple backend support (Triton, vLLM, TGI, Local)
    - Model loading from Model Registry
    - Request queueing & batching
    - Auto-scaling support
    - Health monitoring
    - Request/response logging
    """

    def __init__(
        self,
        model_registry: Optional[ModelRegistry] = None,
        default_backend: InferenceBackend = InferenceBackend.VLLM,
    ):
        self.model_registry = model_registry or get_model_registry()
        self.default_backend = default_backend

        self._backends: Dict[str, InferenceBackendBase] = {}
        self._model_instances: Dict[str, ModelInstance] = {}
        self._request_queue: asyncio.Queue = asyncio.Queue()
        self._worker_tasks: List[asyncio.Task] = []
        self._initialized = False

        # Config
        self.max_batch_size = 32
        self.batch_timeout = 0.1  # seconds
        self.max_queue_size = 1000
        self.worker_count = 4

    async def initialize(self):
        if self._initialized:
            return

        await self.model_registry.initialize()

        # Start worker tasks
        for i in range(self.worker_count):
            task = asyncio.create_task(self._process_queue())
            self._worker_tasks.append(task)

        self._initialized = True
        logger.info("Inference Service initialized")

    async def close(self):
        # Cancel workers
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        # Close backends
        for backend in self._backends.values():
            await backend.close()

        await self.model_registry.close()
        self._initialized = False

    # ==================== Model Loading ====================

    async def load_model(
        self,
        model_name: str,
        version: Optional[int] = None,
        backend: Optional[InferenceBackend] = None,
        endpoint: Optional[str] = None,
    ) -> ModelInstance:
        """Load model from registry into inference backend."""
        if not self._initialized:
            await self.initialize()

        # Get model from registry
        model = await self.model_registry.get_model(model_name)
        if not model:
            raise ValueError(f"Model not found in registry: {model_name}")

        # Get version
        if version is None:
            version_obj = await self.model_registry.get_latest_version(model_name, ModelStage.PRODUCTION)
            if not version_obj:
                version_obj = await self.model_registry.get_latest_version(model_name, ModelStage.STAGING)
            if not version_obj:
                raise ValueError(f"No production/staging version found for {model_name}")
            version = version_obj.version

        # Get version details
        version_obj = await self.model_registry.get_version(model_name, version)
        if not version_obj:
            raise ValueError(f"Version not found: {model_name}/{version}")

        # Determine backend
        backend = backend or self.default_backend
        endpoint = endpoint or self._get_backend_endpoint(backend)

        # Create backend instance
        backend_instance = self._create_backend(backend, endpoint, model_name, version)

        # Initialize backend
        success = await backend_instance.initialize()
        if not success:
            raise RuntimeError(f"Failed to initialize backend for {model_name}")

        # Store instance
        instance_id = f"{model_name}:{version}"
        instance = ModelInstance(
            id=instance_id,
            model_name=model_name,
            model_version=version,
            backend=backend,
            endpoint=endpoint,
            status="ready",
            loaded_at=datetime.utcnow(),
            metadata={
                "backend": backend.value,
                "source": version_obj.source,
                "signature": version_obj.signature.__dict__ if version_obj.signature else None,
            },
        )

        self._backends[instance_id] = backend_instance
        self._model_instances[instance_id] = instance

        logger.info(f"Loaded model: {model_name} v{version} on {backend.value}")
        return instance

    def _get_backend_endpoint(self, backend: InferenceBackend) -> str:
        """Get default endpoint for backend."""
        endpoints = {
            InferenceBackend.TRITON: getattr(settings, 'TRITON_ENDPOINT', 'http://localhost:8000'),
            InferenceBackend.VLLM: getattr(settings, 'VLLM_ENDPOINT', 'http://localhost:8000'),
            InferenceBackend.TGI: getattr(settings, 'TGI_ENDPOINT', 'http://localhost:8080'),
        }
        return endpoints.get(backend, "http://localhost:8000")

    def _create_backend(
        self,
        backend: InferenceBackend,
        endpoint: str,
        model_name: str,
        version: int,
    ) -> InferenceBackendBase:
        if backend == InferenceBackend.TRITON:
            return TritonBackend(endpoint, model_name, version)
        elif backend == InferenceBackend.VLLM:
            return VLLMBackend(endpoint, model_name, version)
        elif backend == InferenceBackend.TGI:
            return TGIBackend(endpoint, model_name, version)
        elif backend == InferenceBackend.LOCAL:
            return LocalBackend(model_name, version, endpoint)
        else:
            raise ValueError(f"Unsupported backend: {backend}")

    async def unload_model(self, model_name: str, version: int):
        """Unload model from memory."""
        instance_id = f"{model_name}:{version}"
        if instance_id in self._backends:
            await self._backends[instance_id].close()
            del self._backends[instance_id]
            del self._model_instances[instance_id]
            logger.info(f"Unloaded model: {model_name} v{version}")

    # ==================== Inference ====================

    async def infer(
        self,
        model_name: str,
        inputs: Dict[str, Any],
        version: Optional[int] = None,
        parameters: Dict[str, Any] = {},
        stream: bool = False,
        priority: int = 0,
        timeout: float = 30.0,
    ) -> InferenceResponse:
        """Run inference on model."""
        if not self._initialized:
            await self.initialize()

        # Ensure model is loaded
        instance_id = f"{model_name}:{version}" if version else model_name
        if instance_id not in self._model_instances:
            if version:
                await self.load_model(model_name, version)
            else:
                # Try to find loaded version
                loaded = [k for k in self._model_instances.keys() if k.startswith(f"{model_name}:")]
                if not loaded:
                    await self.load_model(model_name)
                else:
                    instance_id = loaded[0]

        if instance_id not in self._backends:
            raise ValueError(f"Model not loaded: {model_name}")

        backend = self._backends[instance_id]
        model_instance = self._model_instances[instance_id]

        request = InferenceRequest(
            model_name=model_name,
            model_version=model_instance.model_version,
            inputs=inputs,
            parameters=parameters,
            priority=priority,
            stream=stream,
            timeout=timeout,
        )

        if stream:
            # For streaming, collect all chunks
            full_output = ""
            async for chunk in backend.stream_infer(request):
                if chunk.outputs.get("text"):
                    full_output += chunk.outputs["text"]
                if chunk.status == InferenceStatus.COMPLETED or chunk.status == InferenceStatus.FAILED:
                    return chunk
            # Return final
            return InferenceResponse(
                id=str(uuid4()),
                request_id=request.request_id,
                model_name=model_name,
                model_version=model_instance.model_version,
                outputs={"text": full_output},
                status=InferenceStatus.COMPLETED,
                latency_ms=0,
            )
        else:
            return await backend.infer(request)

    async def stream_infer(
        self,
        model_name: str,
        inputs: Dict[str, Any],
        version: Optional[int] = None,
        parameters: Dict[str, Any] = {},
        timeout: float = 30.0,
    ) -> AsyncGenerator[InferenceResponse, None]:
        """Stream inference."""
        if not self._initialized:
            await self.initialize()

        instance_id = f"{model_name}:{version}" if version else model_name
        if instance_id not in self._backends:
            if version:
                await self.load_model(model_name, version)
            else:
                loaded = [k for k in self._model_instances.keys() if k.startswith(f"{model_name}:")]
                if not loaded:
                    await self.load_model(model_name)
                else:
                    instance_id = loaded[0]

        if instance_id not in self._backends:
            raise ValueError(f"Model not loaded: {model_name}")

        backend = self._backends[instance_id]
        model_instance = self._model_instances[instance_id]

        request = InferenceRequest(
            model_name=model_name,
            model_version=model_instance.model_version,
            inputs=inputs,
            parameters=parameters,
            stream=True,
            timeout=timeout,
        )

        async for chunk in backend.stream_infer(request):
            yield chunk

    async def batch_infer(
        self,
        model_name: str,
        requests: List[Dict[str, Any]],
        version: Optional[int] = None,
    ) -> List[InferenceResponse]:
        """Batch inference for multiple requests."""
        results = []
        for req in requests:
            result = await self.infer(
                model_name=model_name,
                inputs=req.get("inputs", {}),
                version=version,
                parameters=req.get("parameters", {}),
            )
            results.append(result)
        return results

    # ==================== Health & Monitoring ====================

    async def health_check(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Check health of inference service."""
        if not self._initialized:
            await self.initialize()

        if model_name:
            # Check specific model
            instances = [k for k in self._model_instances.keys() if k.startswith(model_name)]
            if not instances:
                return {"status": "not_loaded", "model": model_name}

            instance = self._model_instances[instances[0]]
            backend = self._backends[instances[0]]
            healthy = await backend.health_check()

            return {
                "status": "healthy" if healthy else "unhealthy",
                "model": model_name,
                "version": instance.model_version,
                "backend": instance.backend.value,
            }
        else:
            # Check all models
            results = {}
            for instance_id, backend in self._backends.items():
                instance = self._model_instances[instance_id]
                healthy = await backend.health_check()
                results[instance_id] = {
                    "status": "healthy" if healthy else "unhealthy",
                    "model": instance.model_name,
                    "version": instance.model_version,
                    "backend": instance.backend.value,
                }

            overall = "healthy" if all(r["status"] == "healthy" for r in results.values()) else "degraded"
            return {"overall": overall, "models": results}

    def list_loaded_models(self) -> List[ModelInstance]:
        """List all loaded models."""
        return list(self._model_instances.values())

    # ==================== Queue Processing ====================

    async def _process_queue(self):
        """Process inference requests from queue."""
        while True:
            try:
                request = await asyncio.wait_for(
                    self._request_queue.get(),
                    timeout=1.0,
                )
                # Process request
                await self.infer(
                    model_name=request.model_name,
                    inputs=request.inputs,
                    version=request.model_version,
                    parameters=request.parameters,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processing error: {e}")

    def enqueue_request(self, request: InferenceRequest):
        """Add request to processing queue."""
        try:
            self._request_queue.put_nowait(request)
        except asyncio.QueueFull:
            logger.warning("Inference queue full, request dropped")


# Global inference service instance
_inference_service: Optional[InferenceService] = None


def get_inference_service() -> InferenceService:
    """Get or create inference service singleton."""
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service


def init_inference_service(
    model_registry: Optional[ModelRegistry] = None,
    default_backend: InferenceBackend = InferenceBackend.VLLM,
) -> InferenceService:
    """Initialize inference service with custom config."""
    global _inference_service
    _inference_service = InferenceService(model_registry=model_registry, default_backend=default_backend)
    return _inference_service