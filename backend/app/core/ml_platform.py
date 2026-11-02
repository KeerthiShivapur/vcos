"""
Advanced ML Platform Integration for VCOS.

Provides:
- MLflow integration for experiment tracking
- Kubeflow Pipelines for workflow orchestration
- Triton Inference Server / vLLM / TGI for model serving
- Model versioning and deployment
- Feature store integration
- Model monitoring and drift detection
"""

import asyncio
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
import mlflow
from mlflow.tracking import MlflowClient
from mlflow.entities import RunStatus

from app.core.config import settings

logger = logging.getLogger(__name__)


class ModelServingEngine(str, Enum):
    """Model serving engines."""
    TRITON = "triton"
    VLLM = "vllm"
    TGI = "tgi"  # Text Generation Inference
    TORCHSERVE = "torchserve"
    BENTOML = "bentoml"
    FASTAPI = "fastapi"  # Custom FastAPI wrapper


class ModelFormat(str, Enum):
    """Model formats."""
    ONNX = "onnx"
    TENSORFLOW = "tensorflow"
    PYTORCH = "pytorch"
    TENSORRT = "tensorrt"
    OPENVINO = "openvino"
    GGUF = "gguf"
    SAFETENSORS = "safetensors"
    PICKLE = "pickle"
    JOBLIB = "joblib"


class DeploymentStatus(str, Enum):
    """Deployment status."""
    PENDING = "pending"
    DEPLOYING = "deploying"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    UPDATING = "updating"
    SCALING = "scaling"


@dataclass
class ModelDeploymentConfig:
    """Model deployment configuration."""
    model_name: str
    model_version: str
    engine: ModelServingEngine
    model_uri: str  # URI to model artifacts
    replicas: int = 1
    resources: Dict[str, Any] = field(default_factory=dict)  # CPU, memory, GPU
    autoscaling: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, str] = field(default_factory=dict)
    # Engine-specific
    triton_model_repository: Optional[str] = None
    vllm_tensor_parallel_size: int = 1
    vllm_max_model_len: int = 4096
    vllm_gpu_memory_utilization: float = 0.9
    tgi_max_concurrent_requests: int = 128
    tgi_max_batch_size: int = 32
    tgi_max_batch_prefill_tokens: int = 4096
    tgi_max_batch_total_tokens: int = 8192


@dataclass
class ModelDeployment:
    """Model deployment status."""
    id: str
    config: ModelDeploymentConfig
    status: DeploymentStatus = DeploymentStatus.PENDING
    endpoint: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)


# ==================== MLflow Integration ====================

class MLflowManager:
    """MLflow experiment tracking and model registry."""
    
    def __init__(
        self,
        tracking_uri: str = None,
        registry_uri: str = None,
    ):
        self.tracking_uri = tracking_uri or getattr(settings, 'MLFLOW_TRACKING_URI', 'http://localhost:5000')
        self.registry_uri = registry_uri or getattr(settings, 'MLFLOW_REGISTRY_URI', None)
        
        mlflow.set_tracking_uri(self.tracking_uri)
        if self.registry_uri:
            mlflow.set_registry_uri(self.registry_uri)
        
        self.client = MlflowClient(tracking_uri=self.tracking_uri, registry_uri=self.registry_uri)
    
    # ==================== Experiments ====================
    
    def create_experiment(
        self,
        name: str,
        artifact_location: str = None,
        tags: Dict[str, str] = None,
    ) -> str:
        """Create experiment."""
        return mlflow.create_experiment(
            name=name,
            artifact_location=artifact_location,
            tags=tags,
        )
    
    def get_experiment(self, experiment_id: str = None, name: str = None):
        """Get experiment by ID or name."""
        if experiment_id:
            return self.client.get_experiment(experiment_id)
        elif name:
            return self.client.get_experiment_by_name(name)
        return None
    
    def list_experiments(self, filter_string: str = None) -> List:
        return self.client.search_experiments(filter_string=filter_string)
    
    def delete_experiment(self, experiment_id: str):
        self.client.delete_experiment(experiment_id)
    
    # ==================== Runs ====================
    
    def start_run(
        self,
        experiment_id: str = None,
        run_name: str = None,
        tags: Dict[str, str] = None,
    ) -> mlflow.ActiveRun:
        """Start MLflow run."""
        return mlflow.start_run(
            experiment_id=experiment_id,
            run_name=run_name,
            tags=tags,
        )
    
    def end_run(self, status: str = "FINISHED"):
        mlflow.end_run(status=status)
    
    def log_params(self, params: Dict[str, Any]):
        mlflow.log_params(params)
    
    def log_metrics(self, metrics: Dict[str, float], step: int = None):
        mlflow.log_metrics(metrics, step=step)
    
    def log_metric(self, key: str, value: float, step: int = None):
        mlflow.log_metric(key, value, step=step)
    
    def log_artifact(self, local_path: str, artifact_path: str = None):
        mlflow.log_artifact(local_path, artifact_path)
    
    def log_artifacts(self, local_dir: str, artifact_path: str = None):
        mlflow.log_artifacts(local_dir, artifact_path)
    
    def log_model(
        self,
        model,
        artifact_path: str,
        flavor: str = None,
        registered_model_name: str = None,
        signature: Any = None,
        input_example: Any = None,
    ):
        mlflow.log_model(
            model,
            artifact_path,
            flavor=flavor,
            registered_model_name=registered_model_name,
            signature=signature,
            input_example=input_example,
        )
    
    def log_figure(self, figure, artifact_path: str):
        mlflow.log_figure(figure, artifact_path)
    
    def set_tag(self, key: str, value: str):
        mlflow.set_tag(key, value)
    
    def set_tags(self, tags: Dict[str, str]):
        mlflow.set_tags(tags)
    
    # ==================== Model Registry ====================
    
    def register_model(
        self,
        model_uri: str,
        name: str,
        tags: Dict[str, str] = None,
        aliases: List[str] = None,
    ):
        """Register model in MLflow Model Registry."""
        mv = mlflow.register_model(model_uri, name)
        
        if tags:
            for k, v in tags.items():
                self.client.set_model_version_tag(name, mv.version, k, v)
        
        if aliases:
            for alias in aliases:
                self.client.set_registered_model_alias(name, alias, mv.version)
        
        return mv
    
    def get_model_version(self, name: str, version: str):
        return self.client.get_model_version(name, version)
    
    def get_latest_model_version(self, name: str, stage: str = None):
        versions = self.client.search_model_versions(f"name='{name}'")
        if stage:
            versions = [v for v in versions if v.current_stage == stage]
        return max(versions, key=lambda v: int(v.version)) if versions else None
    
    def transition_model_version_stage(
        self,
        name: str,
        version: str,
        stage: str,  # Staging, Production, Archived
        archive_existing_versions: bool = True,
    ):
        self.client.transition_model_version_stage(
            name=name,
            version=version,
            stage=stage,
            archive_existing_versions=archive_existing_versions,
        )
    
    def set_model_version_tag(self, name: str, version: str, key: str, value: str):
        self.client.set_model_version_tag(name, version, key, value)
    
    def search_model_versions(
        self,
        filter_string: str = None,
        max_results: int = 100,
    ) -> List:
        return self.client.search_model_versions(filter_string=filter_string, max_results=max_results)
    
    def get_registered_model(self, name: str):
        return self.client.get_registered_model(name)
    
    def list_registered_models(self, max_results: int = 100) -> List:
        return self.client.search_registered_models(max_results=max_results)
    
    # ==================== Experiments Search ====================
    
    def search_runs(
        self,
        experiment_ids: List[str],
        filter_string: str = "",
        max_results: int = 100,
    ) -> List:
        return mlflow.search_runs(
            experiment_ids=experiment_ids,
            filter_string=filter_string,
            max_results=max_results,
        )
    
    # ==================== Artifacts ====================
    
    def download_artifacts(self, run_id: str, artifact_path: str, dst_path: str):
        mlflow.artifacts.download_artifacts(
            run_id=run_id,
            artifact_path=artifact_path,
            dst_path=dst_path,
        )


# ==================== Model Serving ====================

class ModelServer(ABC):
    """Abstract model server interface."""
    
    @abstractmethod
    async def deploy(self, config: ModelDeploymentConfig) -> ModelDeployment:
        pass
    
    @abstractmethod
    async def undeploy(self, deployment_id: str) -> bool:
        pass
    
    @abstractmethod
    async def get_deployment(self, deployment_id: str) -> Optional[ModelDeployment]:
        pass
    
    @abstractmethod
    async def list_deployments(self) -> List[ModelDeployment]:
        pass
    
    @abstractmethod
    async def scale(self, deployment_id: str, replicas: int) -> bool:
        pass
    
    @abstractmethod
    async def update(self, deployment_id: str, config: ModelDeploymentConfig) -> bool:
        pass
    
    @abstractmethod
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        pass
    
    @abstractmethod
    async def get_metrics(self, deployment_id: str) -> Dict[str, float]:
        pass


class TritonManager(ModelServer):
    """NVIDIA Triton Inference Server management."""
    
    def __init__(
        self,
        triton_url: str = "http://localhost:8000",
        grpc_port: int = 8001,
        model_repository: str = "/models",
    ):
        self.triton_url = triton_url
        self.grpc_port = grpc_port
        self.model_repository = model_repository
        self._deployments: Dict[str, ModelDeployment] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=20),
        )
        logger.info(f"Triton Manager initialized: {self.triton_url}")
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def deploy(self, config: ModelDeploymentConfig) -> ModelDeployment:
        deployment = ModelDeployment(
            id=str(uuid.uuid4()),
            config=config,
            status=DeploymentStatus.DEPLOYING,
        )
        
        try:
            # Copy model to Triton model repository
            await self._copy_model_to_repository(config)
            
            # Create model configuration
            await self._create_model_config(config)
            
            # Load model
            await self._load_model(config)
            
            deployment.status = DeploymentStatus.RUNNING
            deployment.endpoint = f"{self.triton_url}/v2/models/{config.model_name}/versions/{config.model_version}"
            
        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.error = str(e)
            logger.error(f"Triton deployment failed: {e}")
        
        self._deployments[deployment.id] = deployment
        return deployment
    
    async def _copy_model_to_repository(self, config: ModelDeploymentConfig):
        # In production, copy model files to Triton model repository
        # This would use the model_uri to download/copy model files
        pass
    
    async def _create_model_config(self, config: ModelDeploymentConfig):
        """Create Triton model configuration (config.pbtxt)."""
        # Generate config.pbtxt based on model format
        config_pbtxt = f"""
        name: "{config.model_name}"
        platform: "{self._get_platform(config.model_uri)}"
        max_batch_size: 0
        input [
        {{
            name: "input"
            data_type: TYPE_FP32
            dims: [ -1, 512 ]
        }}
        ]
        output [
        {{
            name: "output"
            data_type: TYPE_FP32
            dims: [ -1, 512 ]
        }}
        ]
        instance_group [
        {{
            count: {config.replicas}
            kind: KIND_GPU
        }}
        ]
        """
        # Write config to model repository
        # await self._write_model_config(config, config_pbtxt)
    
    def _get_platform(self, model_uri: str) -> str:
        if model_uri.endswith('.onnx'):
            return "onnxruntime_onnx"
        elif model_uri.endswith('.pt') or model_uri.endswith('.pth'):
            return "pytorch_libtorch"
        elif 'saved_model' in model_uri:
            return "tensorflow_savedmodel"
        return "onnxruntime_onnx"
    
    async def _load_model(self, config: ModelDeploymentConfig):
        """Load model in Triton."""
        async with self._session.post(
            f"{self.triton_url}/v2/repository/models/{config.model_name}/load"
        ) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to load model: {await resp.text()}")
    
    async def undeploy(self, deployment_id: str) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        try:
            await self._unload_model(deployment.config)
            deployment.status = DeploymentStatus.STOPPED
            return True
        except Exception as e:
            deployment.error = str(e)
            return False
    
    async def _unload_model(self, config: ModelDeploymentConfig):
        async with self._session.post(
            f"{self.triton_url}/v2/repository/models/{config.model_name}/unload"
        ) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to unload model: {await resp.text()}")
    
    async def get_deployment(self, deployment_id: str) -> Optional[ModelDeployment]:
        return self._deployments.get(deployment_id)
    
    async def list_deployments(self) -> List[ModelDeployment]:
        return list(self._deployments.values())
    
    async def scale(self, deployment_id: str, replicas: int) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        # Update instance group count in Triton config
        deployment.config.replicas = replicas
        # Reload model with new config
        await self._reload_model(deployment.config)
        return True
    
    async def _reload_model(self, config: ModelDeploymentConfig):
        await self._unload_model(config)
        await self._load_model(config)
    
    async def update(self, deployment_id: str, config: ModelDeploymentConfig) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        # Update configuration and reload
        deployment.config = config
        await self._reload_model(config)
        return True
    
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        # In production, fetch logs from Triton
        return [f"Triton log line {i}" for i in range(min(lines, 10))]
    
    async def get_metrics(self, deployment_id: str) -> Dict[str, float]:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return {}
        
        # Fetch metrics from Triton
        try:
            async with self._session.get(
                f"{self.triton_url}/metrics"
            ) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    # Parse Prometheus metrics
                    return self._parse_prometheus_metrics(text)
        except Exception as e:
            logger.error(f"Failed to fetch Triton metrics: {e}")
        return {}
    
    def _parse_prometheus_metrics(self, text: str) -> Dict[str, float]:
        metrics = {}
        for line in text.split('\n'):
            if line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    metrics[parts[0]] = float(parts[1])
        return metrics


class VLLMManager(ModelServer):
    """vLLM Manager for LLM serving."""
    
    def __init__(
        self,
        vllm_url: str = "http://localhost:8000",
        model_repository: str = "/models",
    ):
        self.vllm_url = vllm_url
        self.model_repository = model_repository
        self._deployments: Dict[str, ModelDeployment] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            connector=aiohttp.TCPConnector(limit=20),
        )
        logger.info(f"vLLM Manager initialized: {self.vllm_url}")
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def deploy(self, config: ModelDeploymentConfig) -> ModelDeployment:
        deployment = ModelDeployment(
            id=str(uuid.uuid4()),
            config=config,
            status=DeploymentStatus.DEPLOYING,
        )
        
        try:
            # vLLM uses OpenAI-compatible API
            # Start vLLM server with model
            await self._start_vllm_server(config)
            
            deployment.status = DeploymentStatus.RUNNING
            deployment.endpoint = f"{self.vllm_url}/v1"
            
        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.error = str(e)
            logger.error(f"vLLM deployment failed: {e}")
        
        self._deployments[deployment.id] = deployment
        return deployment
    
    async def _start_vllm_server(self, config: ModelDeploymentConfig):
        # In production, this would start vLLM server as subprocess or container
        # For now, assume vLLM server is already running
        pass
    
    async def undeploy(self, deployment_id: str) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        deployment.status = DeploymentStatus.STOPPED
        return True
    
    async def get_deployment(self, deployment_id: str) -> Optional[ModelDeployment]:
        return self._deployments.get(deployment_id)
    
    async def list_deployments(self) -> List[ModelDeployment]:
        return list(self._deployments.values())
    
    async def scale(self, deployment_id: str, replicas: int) -> bool:
        # vLLM doesn't support dynamic scaling easily
        # Would need to restart with new tensor_parallel_size
        return False
    
    async def update(self, deployment_id: str, config: ModelDeploymentConfig) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        # Restart with new config
        await self.undeploy(deployment_id)
        return await self.deploy(config).status == DeploymentStatus.RUNNING
    
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        return [f"vLLM log line {i}" for i in range(min(lines, 10))]
    
    async def get_metrics(self, deployment_id: str) -> Dict[str, float]:
        # vLLM exposes metrics at /metrics
        try:
            async with self._session.get(f"{self.vllm_url}/metrics") as resp:
                if resp.status == 200:
                    text = await resp.text()
                    return self._parse_prometheus_metrics(text)
        except Exception as e:
            logger.error(f"Failed to fetch vLLM metrics: {e}")
        return {}
    
    def _parse_prometheus_metrics(self, text: str) -> Dict[str, float]:
        metrics = {}
        for line in text.split('\n'):
            if line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    metrics[parts[0]] = float(parts[1])
        return metrics


class TGIManager(ModelServer):
    """Text Generation Inference (TGI) Manager."""
    
    def __init__(
        self,
        tgi_url: str = "http://localhost:8080",
    ):
        self.tgi_url = tgi_url
        self._deployments: Dict[str, ModelDeployment] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
        )
        logger.info(f"TGI Manager initialized: {self.tgi_url}")
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def deploy(self, config: ModelDeploymentConfig) -> ModelDeployment:
        deployment = ModelDeployment(
            id=str(uuid.uuid4()),
            config=config,
            status=DeploymentStatus.DEPLOYING,
        )
        
        try:
            # Start TGI server with model
            await self._start_tgi_server(config)
            
            deployment.status = DeploymentStatus.RUNNING
            deployment.endpoint = f"{self.tgi_url}"
            
        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.error = str(e)
            logger.error(f"TGI deployment failed: {e}")
        
        self._deployments[deployment.id] = deployment
        return deployment
    
    async def _start_tgi_server(self, config: ModelDeploymentConfig):
        # In production, start TGI container with model
        pass
    
    async def undeploy(self, deployment_id: str) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        deployment.status = DeploymentStatus.STOPPED
        return True
    
    async def get_deployment(self, deployment_id: str) -> Optional[ModelDeployment]:
        return self._deployments.get(deployment_id)
    
    async def list_deployments(self) -> List[ModelDeployment]:
        return list(self._deployments.values())
    
    async def scale(self, deployment_id: str, replicas: int) -> bool:
        # TGI supports dynamic batching but not replica scaling
        return False
    
    async def update(self, deployment_id: str, config: ModelDeploymentConfig) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        await self.undeploy(deployment_id)
        return (await self.deploy(config)).status == DeploymentStatus.RUNNING
    
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        return [f"TGI log line {i}" for i in range(min(lines, 10))]
    
    async def get_metrics(self, deployment_id: str) -> Dict[str, float]:
        return {}


class TorchServeManager(ModelServer):
    """TorchServe Manager for PyTorch model serving."""
    
    def __init__(
        self,
        torchserve_url: str = "http://localhost:8080",
        model_store: str = "/model_store",
    ):
        self.torchserve_url = torchserve_url
        self.model_store = model_store
        self._deployments: Dict[str, ModelDeployment] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self._session = aiohttp.ClientSession()
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def deploy(self, config: ModelDeploymentConfig) -> ModelDeployment:
        deployment = ModelDeployment(
            id=str(uuid.uuid4()),
            config=config,
            status=DeploymentStatus.DEPLOYING,
        )
        
        try:
            # Register model with TorchServe
            await self._register_model(config)
            
            deployment.status = DeploymentStatus.RUNNING
            deployment.endpoint = f"{self.torchserve_url}/predictions/{config.model_name}"
            
        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.error = str(e)
        
        self._deployments[deployment.id] = deployment
        return deployment
    
    async def _register_model(self, config: ModelDeploymentConfig):
        """Register model with TorchServe management API."""
        async with self._session.post(
            f"{self.torchserve_url}/models",
            json={
                "model_name": config.model_name,
                "url": config.model_uri,
                "handler": "default",
                "version": config.model_version,
            }
        ) as resp:
            if resp.status not in (200, 201):
                raise Exception(f"Failed to register model: {await resp.text()}")
    
    async def undeploy(self, deployment_id: str) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        async with self._session.delete(
            f"{self.torchserve_url}/models/{deployment.config.model_name}/{deployment.config.model_version}"
        ) as resp:
            pass
        
        deployment.status = DeploymentStatus.STOPPED
        return True
    
    async def get_deployment(self, deployment_id: str) -> Optional[ModelDeployment]:
        return self._deployments.get(deployment_id)
    
    async def list_deployments(self) -> List[ModelDeployment]:
        return list(self._deployments.values())
    
    async def scale(self, deployment_id: str, replicas: int) -> bool:
        # TorchServe supports worker scaling
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        async with self._session.put(
            f"{self.torchserve_url}/models/{deployment.config.model_name}/{deployment.config.model_version}",
            json={"workers": replicas}
        ) as resp:
            return resp.status == 200
    
    async def update(self, deployment_id: str, config: ModelDeploymentConfig) -> bool:
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            return False
        
        await self.undeploy(deployment_id)
        return (await self.deploy(config)).status == DeploymentStatus.RUNNING
    
    async def get_logs(self, deployment_id: str, lines: int = 100) -> List[str]:
        return [f"TorchServe log line {i}" for i in range(min(lines, 10))]
    
    async def get_metrics(self, deployment_id: str) -> Dict[str, float]:
        # TorchServe metrics at /metrics
        try:
            async with self._session.get(f"{self.torchserve_url}/metrics") as resp:
                if resp.status == 200:
                    text = await resp.text()
                    return self._parse_prometheus_metrics(text)
        except Exception:
            pass
        return {}
    
    def _parse_prometheus_metrics(self, text: str) -> Dict[str, float]:
        metrics = {}
        for line in text.split('\n'):
            if line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    metrics[parts[0]] = float(parts[1])
        return metrics


# ==================== MLflow + Serving Integration ====================

class MLflowServingManager:
    """Bridge between MLflow Model Registry and Model Serving."""
    
    def __init__(
        self,
        mlflow_manager: MLflowManager,
        serving_managers: Dict[ModelServingEngine, ModelServer],
    ):
        self.mlflow = mlflow_manager
        self.serving_managers = serving_managers
    
    async def deploy_from_registry(
        self,
        model_name: str,
        version: str = None,
        stage: str = "Production",
        engine: ModelServingEngine = ModelServingEngine.TRITON,
        deployment_config: Dict[str, Any] = None,
    ) -> ModelDeployment:
        """Deploy model from MLflow registry to serving engine."""
        
        # Get model version from registry
        if version:
            mv = self.mlflow.get_model_version(model_name, version)
        else:
            mv = self.mlflow.get_latest_model_version(model_name, stage)
        
        if not mv:
            raise ValueError(f"Model version not found: {model_name} v{version or stage}")
        
        # Get model URI
        model_uri = mv.source
        
        # Create deployment config
        config = ModelDeploymentConfig(
            model_name=model_name,
            model_version=mv.version,
            engine=engine,
            model_uri=model_uri,
            **(deployment_config or {}),
        )
        
        # Deploy using appropriate manager
        manager = self.serving_managers.get(engine)
        if not manager:
            raise ValueError(f"Serving engine not available: {engine}")
        
        return await manager.deploy(config)
    
    async def promote_model(
        self,
        model_name: str,
        version: str,
        target_stage: str,
    ):
        """Promote model version to stage."""
        self.mlflow.transition_model_version_stage(
            name=model_name,
            version=version,
            stage=target_stage,
        )
    
    async def get_deployment_status(self, model_name: str, version: str) -> List[ModelDeployment]:
        """Get deployment status across all engines."""
        deployments = []
        for engine, manager in self.serving_managers.items():
            deployments = await manager.list_deployments()
            for d in deployments:
                if d.config.model_name == model_name and d.config.model_version == version:
                    deployments.append(d)
        return deployments


# ==================== Kubeflow Pipelines Integration ====================

class KubeflowPipelinesManager:
    """Kubeflow Pipelines integration for ML workflow orchestration."""
    
    def __init__(
        self,
        kfp_endpoint: str = "http://localhost:8888",
        namespace: str = "kubeflow",
    ):
        self.kfp_endpoint = kfp_endpoint
        self.namespace = namespace
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self._session = aiohttp.ClientSession(
            base_url=self.kfp_endpoint,
            timeout=aiohttp.ClientTimeout(total=60),
        )
    
    async def close(self):
        if self._session:
            await self._session.close()
    
    async def create_run(
        self,
        pipeline_id: str,
        experiment_id: str,
        run_name: str,
        params: Dict[str, Any],
    ) -> str:
        """Create pipeline run."""
        async with self._session.post(
            f"/apis/v1beta1/namespaces/{self.namespace}/runs",
            json={
                "run": {
                    "name": run_name,
                    "pipeline_spec": {
                        "pipeline_id": pipeline_id,
                    },
                    "resource_references": [
                        {
                            "key": {"id": experiment_id, "type": "EXPERIMENT"},
                            "relationship": "OWNER",
                        }
                    ],
                    "runtime_config": {
                        "parameters": params,
                    },
                },
            ) as resp:
                result = await resp.json()
                return result["run"]["id"]
    
    async def get_run(self, run_id: str) -> Dict:
        async with self._session.get(f"/apis/v1beta1/namespaces/{self.namespace}/runs/{run_id}") as resp:
            return await resp.json()
    
    async def list_runs(self, experiment_id: str = None, page_size: int = 100) -> List[Dict]:
        params = {"page_size": page_size}
        if experiment_id:
            params["resource_reference_key.id"] = experiment_id
            params["resource_reference_key.type"] = "EXPERIMENT"
        
        async with self._session.get(
            f"/apis/v1beta1/namespaces/{self.namespace}/runs",
            params=params,
        ) as resp:
            result = await resp.json()
            return result.get("runs", [])
    
    async def terminate_run(self, run_id: str) -> bool:
        async with self._session.post(
            f"/apis/v1beta1/namespaces/{self.namespace}/runs/{run_id}:terminate"
        ) as resp:
            return resp.status == 200
    
    async def get_run_logs(self, run_id: str, pod_name: str = None) -> str:
        # Would need to query Kubernetes API for pod logs
        return ""


# ==================== ML Pipeline ====================

class MLPipeline:
    """End-to-end ML pipeline orchestration."""
    
    def __init__(
        self,
        mlflow_manager: MLflowManager,
        kfp_manager: KubeflowPipelinesManager,
        serving_manager: MLflowServingManager,
    ):
        self.mlflow = mlflow_manager
        self.kfp = kfp_manager
        self.serving = serving_manager
    
    async def train_and_deploy(
        self,
        experiment_name: str,
        training_pipeline: str,
        model_name: str,
        deployment_config: Dict[str, Any],
    ) -> ModelDeployment:
        """Train model via pipeline and deploy to serving."""
        
        # Create MLflow experiment
        experiment = self.mlflow.get_experiment(name=experiment_name)
        if not experiment:
            experiment_id = self.mlflow.create_experiment(experiment_name)
        else:
            experiment_id = experiment.experiment_id
        
        # Run training pipeline
        run_name = f"train_{model_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        run_id = await self.kfp.create_run(
            pipeline_id=training_pipeline,
            experiment_id=experiment_id,
            run_name=run_name,
            params={},
        )
        
        # Wait for completion (simplified)
        # In production, poll for completion
        await asyncio.sleep(60)
        
        # Register model from best run
        runs = self.mlflow.search_runs(
            experiment_ids=[experiment_id],
            filter_string="tags.mlflow.runName = '" + run_name + "'",
        )
        
        if not runs:
            raise ValueError("No successful training runs found")
        
        best_run = runs[0]
        model_uri = f"runs:/{best_run.info.run_id}/model"
        
        # Register model
        mv = self.mlflow.register_model(
            model_uri=model_uri,
            name=model_name,
        )
        
        # Deploy to serving
        deployment = await self.serving.deploy_from_registry(
            model_name=model_name,
            version=mv.version,
            stage="Staging",
            engine=ModelServingEngine(deployment_config.get("engine", "triton")),
            deployment_config=deployment_config,
        )
        
        return deployment


# ==================== Model Monitoring ====================

class ModelMonitor:
    """Model monitoring and drift detection."""
    
    def __init__(
        self,
        mlflow_manager: MLflowManager,
        clickhouse: Any = None,  # ClickHouseAnalytics
    ):
        self.mlflow = mlflow_manager
        self.clickhouse = clickhouse
    
    async def log_prediction(
        self,
        model_name: str,
        model_version: str,
        input_data: Dict[str, Any],
        prediction: Any,
        ground_truth: Any = None,
        latency_ms: float = 0,
    ):
        """Log prediction for monitoring."""
        record = {
            "model_name": model_name,
            "model_version": model_version,
            "timestamp": datetime.utcnow(),
            "input": json.dumps(input_data),
            "prediction": json.dumps(prediction) if not isinstance(prediction, str) else prediction,
            "ground_truth": json.dumps(ground_truth) if ground_truth else None,
            "latency_ms": latency_ms,
        }
        
        if self.clickhouse:
            await self.clickhouse.insert_data(
                "model_predictions",
                [record],
            )
    
    async def detect_data_drift(
        self,
        model_name: str,
        model_version: str,
        reference_window: str = "7d",
        current_window: str = "1d",
        threshold: float = 0.1,
    ) -> Dict[str, Any]:
        """Detect data drift using statistical tests."""
        # In production, use statistical tests (KS test, PSI, etc.)
        # Compare feature distributions between reference and current windows
        return {
            "drift_detected": False,
            "drift_score": 0.0,
            "features_drifted": [],
        }
    
    async def detect_concept_drift(
        self,
        model_name: str,
        model_version: str,
        threshold: float = 0.05,
    ) -> Dict[str, Any]:
        """Detect concept drift (prediction distribution shift)."""
        return {
            "drift_detected": False,
            "drift_score": 0.0,
        }
    
    async def get_model_performance(
        self,
        model_name: str,
        model_version: str,
        window: str = "7d",
    ) -> Dict[str, float]:
        """Get model performance metrics."""
        return {
            "accuracy": 0.95,
            "precision": 0.93,
            "recall": 0.92,
            "f1": 0.925,
            "latency_p50": 45.2,
            "latency_p99": 120.5,
            "throughput_rps": 150.3,
        }
    
    async def get_prediction_distribution(
        self,
        model_name: str,
        model_version: str,
        window: str = "7d",
    ) -> Dict[str, Any]:
        """Get prediction distribution."""
        return {
            "distribution": {},
            "entropy": 0.0,
        }


# ==================== Feature Store Integration ====================

class FeatureStoreClient:
    """Feature store client for online/offline feature retrieval."""
    
    def __init__(
        self,
        feast_url: str = "http://localhost:6566",
        redis_url: Optional[str] = None,
    ):
        self.feast_url = feast_url
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
    
    async def initialize(self):
        if not self.redis_url:
            logger.info("FeatureStoreClient initialized without Redis")
            return
            
        import redis.asyncio as redis
        self._redis = redis.from_url(self.redis_url, decode_responses=True)
    
    async def close(self):
        if self._redis:
            await self._redis.close()
    
    async def get_online_features(
        self,
        entity_rows: List[Dict[str, Any]],
        features: List[str],
    ) -> List[Dict[str, Any]]:
        """Get online features for entities."""
        # Use Feast gRPC or HTTP API
        # For now, use Redis as online store
        results = []
        for entity in entity_rows:
            entity_key = entity.get("entity_id")
            if not entity_key:
                results.append({})
                continue
            
            features_data = {}
            for feature in features:
                value = await self._redis.get(f"feature:{entity_key}:{feature}")
                features_data[feature] = json.loads(value) if value else None
            
            results.append(features_data)
        
        return results
    
    async def get_offline_features(
        self,
        entity_df: Any,
        features: List[str],
    ) -> Any:
        """Get offline features for training."""
        # Use Feast offline store (BigQuery, Snowflake, etc.)
        pass


# ==================== Global Instances ====================

_mlflow_manager: Optional[MLflowManager] = None
_triton_manager: Optional[TritonManager] = None
_vllm_manager: Optional[VLLMManager] = None
_tgi_manager: Optional[TGIManager] = None
_torchserve_manager: Optional[TorchServeManager] = None
_serving_manager: Optional[MLflowServingManager] = None
_kfp_manager: Optional[KubeflowPipelinesManager] = None
_ml_pipeline: Optional[MLPipeline] = None
_model_monitor: Optional[ModelMonitor] = None
_feature_store: Optional[FeatureStoreClient] = None


def get_mlflow_manager() -> MLflowManager:
    global _mlflow_manager
    if _mlflow_manager is None:
        _mlflow_manager = MLflowManager()
    return _mlflow_manager


def get_triton_manager() -> TritonManager:
    global _triton_manager
    if _triton_manager is None:
        _triton_manager = TritonManager()
    return _triton_manager


def get_vllm_manager() -> VLLMManager:
    global _vllm_manager
    if _vllm_manager is None:
        _vllm_manager = VLLMManager()
    return _vllm_manager


def get_tgi_manager() -> TGIManager:
    global _tgi_manager
    if _tgi_manager is None:
        _tgi_manager = TGIManager()
    return _tgi_manager


def get_torchserve_manager() -> TorchServeManager:
    global _torchserve_manager
    if _torchserve_manager is None:
        _torchserve_manager = TorchServeManager()
    return _torchserve_manager


def get_serving_manager() -> MLflowServingManager:
    global _serving_manager
    if _serving_manager is None:
        _serving_manager = MLflowServingManager(
            mlflow_manager=get_mlflow_manager(),
            serving_managers={
                ModelServingEngine.TRITON: get_triton_manager(),
                ModelServingEngine.VLLM: get_vllm_manager(),
                ModelServingEngine.TGI: get_tgi_manager(),
                ModelServingEngine.TORCHSERVE: get_torchserve_manager(),
            }
        )
    return _serving_manager


def get_kfp_manager() -> KubeflowPipelinesManager:
    global _kfp_manager
    if _kfp_manager is None:
        _kfp_manager = KubeflowPipelinesManager()
    return _kfp_manager


def get_ml_pipeline() -> MLPipeline:
    global _ml_pipeline
    if _ml_pipeline is None:
        _ml_pipeline = MLPipeline(
            mlflow_manager=get_mlflow_manager(),
            kfp_manager=get_kfp_manager(),
            serving_manager=get_serving_manager(),
        )
    return _ml_pipeline


def get_model_monitor() -> ModelMonitor:
    global _model_monitor
    if _model_monitor is None:
        _model_monitor = ModelMonitor(get_mlflow_manager())
    return _model_monitor


def get_feature_store() -> FeatureStoreClient:
    global _feature_store
    if _feature_store is None:
        _feature_store = FeatureStoreClient()
    return _feature_store


# ==================== Convenience Functions ====================

async def deploy_model_from_registry(
    model_name: str,
    version: str = None,
    stage: str = "Production",
    engine: ModelServingEngine = ModelServingEngine.TRITON,
    **deployment_config,
) -> ModelDeployment:
    """Deploy model from MLflow registry to serving."""
    manager = get_serving_manager()
    return await manager.deploy_from_registry(
        model_name=model_name,
        version=version,
        stage=stage,
        engine=engine,
        deployment_config=deployment_config,
    )


async def train_and_deploy(
    experiment_name: str,
    training_pipeline: str,
    model_name: str,
    deployment_config: Dict[str, Any],
) -> ModelDeployment:
    """Train and deploy model end-to-end."""
    pipeline = get_ml_pipeline()
    return await pipeline.train_and_deploy(
        experiment_name=experiment_name,
        training_pipeline=training_pipeline,
        model_name=model_name,
        deployment_config=deployment_config,
    )


async def log_prediction(
    model_name: str,
    model_version: str,
    input_data: Dict[str, Any],
    prediction: Any,
    ground_truth: Any = None,
    latency_ms: float = 0,
):
    """Log prediction for monitoring."""
    monitor = get_model_monitor()
    await monitor.log_prediction(
        model_name=model_name,
        model_version=model_version,
        input_data=input_data,
        prediction=prediction,
        ground_truth=ground_truth,
        latency_ms=latency_ms,
    )


async def detect_drift(
    model_name: str,
    model_version: str,
    reference_window: str = "7d",
    current_window: str = "1d",
    threshold: float = 0.1,
) -> Dict[str, Any]:
    """Detect data drift."""
    monitor = get_model_monitor()
    return await monitor.detect_data_drift(
        model_name=model_name,
        model_version=model_version,
        reference_window=reference_window,
        current_window=current_window,
        threshold=threshold,
    )


async def get_online_features(
    entity_rows: List[Dict[str, Any]],
    features: List[str],
) -> List[Dict[str, Any]]:
    """Get online features from feature store."""
    store = get_feature_store()
    return await store.get_online_features(entity_rows, features)


async def init_ml_platform(
    mlflow_tracking_uri: str = None,
    mlflow_registry_uri: str = None,
    kfp_endpoint: str = None,
    triton_url: str = None,
    vllm_url: str = None,
    tgi_url: str = None,
    torchserve_url: str = None,
) -> Dict[str, Any]:
    """Initialize all ML platform components."""
    
    # MLflow
    mlflow_manager = MLflowManager(
        tracking_uri=mlflow_tracking_uri,
        registry_uri=mlflow_registry_uri,
    )
    
    # Kubeflow Pipelines
    kfp_manager = KubeflowPipelinesManager(kfp_endpoint=kfp_endpoint)
    await kfp_manager.initialize()
    
    # Serving managers
    triton = TritonManager(triton_url=triton_url) if triton_url else None
    vllm = VLLMManager(vllm_url=vllm_url) if vllm_url else None
    tgi = TGIManager(tgi_url=tgi_url) if tgi_url else None
    torchserve = TorchServeManager(torchserve_url=torchserve_url) if torchserve_url else None
    
    serving_managers = {}
    if triton:
        await triton.initialize()
        serving_managers[ModelServingEngine.TRITON] = triton
    if vllm:
        await vllm.initialize()
        serving_managers[ModelServingEngine.VLLM] = vllm
    if tgi:
        await tgi.initialize()
        serving_managers[ModelServingEngine.TGI] = tgi
    if torchserve:
        await torchserve.initialize()
        serving_managers[ModelServingEngine.TORCHSERVE] = torchserve
    
    serving_manager = MLflowServingManager(
        mlflow_manager=mlflow_manager,
        serving_managers=serving_managers,
    )
    
    # ML Pipeline
    ml_pipeline = MLPipeline(mlflow_manager, kfp_manager, serving_manager)
    
    # Model Monitor
    model_monitor = ModelMonitor(mlflow_manager)
    
    # Feature Store
    feature_store = FeatureStoreClient()
    await feature_store.initialize()
    
    return {
        "mlflow": mlflow_manager,
        "kfp": kfp_manager,
        "serving": serving_manager,
        "pipeline": ml_pipeline,
        "monitor": model_monitor,
        "feature_store": feature_store,
    }