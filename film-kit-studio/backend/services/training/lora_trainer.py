"""
LoRA Training Pipeline — Submits training jobs to Modal/RunPod/RunHouse.

Supports:
- Modal (modal.com) — serverless GPU, great for spot instances
- RunPod — pod-based, persistent storage
- RunHouse — cluster management
- Local (if GPU available)

Uses kohya-ss / simpletuner under the hood.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# TRAINING BACKENDS
# ════════════════════════════════════════════════════════════════════════════

class TrainingBackend(str, Enum):
    MODAL = "modal"
    RUNPOD = "runpod"
    RUNHOUSE = "runhouse"
    LOCAL = "local"


class TrainingStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ════════════════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════════════════

class LoRATrainingConfig:
    """Configuration for LoRA training."""

    def __init__(
        self,
        # Model
        base_model: str = "stabilityai/stable-diffusion-xl-base-1.0",
        model_type: str = "sdxl",  # sdxl | sd15 | sd21

        # Dataset
        dataset_dir: str = "",
        resolution: int = 512,
        batch_size: int = 1,

        # LoRA
        lora_rank: int = 32,
        lora_alpha: int = 32,
        lora_dropout: float = 0.0,
        network_module: str = "networks.lora",
        network_dim: int = 32,  # alias for rank

        # Training
        max_train_steps: int = 1000,
        learning_rate: float = 1e-4,
        lr_scheduler: str = "cosine_with_restarts",
        lr_warmup_steps: int = 100,
        optimizer: str = "AdamW8bit",
        mixed_precision: str = "fp16",
        gradient_accumulation_steps: int = 1,

        # Advanced
        noise_offset: float = 0.0,
        min_snr_gamma: float = 5.0,
        scale_lr: bool = False,
        cache_latents: bool = True,
        cache_latents_to_disk: bool = False,

        # Validation
        validation_prompt: str = "",
        validation_steps: int = 100,
        validation_images: int = 4,

        # Output
        output_dir: str = "./loras",
        save_every_n_steps: int = 500,
        save_precision: str = "fp16",

        # Hardware
        gpu_type: str = "A100-40GB",
        num_gpus: int = 1,
    ):
        self.base_model = base_model
        self.model_type = model_type
        self.dataset_dir = dataset_dir
        self.resolution = resolution
        self.batch_size = batch_size
        self.lora_rank = lora_rank
        self.lora_alpha = lora_alpha
        self.lora_dropout = lora_dropout
        self.network_module = network_module
        self.network_dim = network_dim
        self.max_train_steps = max_train_steps
        self.learning_rate = learning_rate
        self.lr_scheduler = lr_scheduler
        self.lr_warmup_steps = lr_warmup_steps
        self.optimizer = optimizer
        self.mixed_precision = mixed_precision
        self.gradient_accumulation_steps = gradient_accumulation_steps
        self.noise_offset = noise_offset
        self.min_snr_gamma = min_snr_gamma
        self.scale_lr = scale_lr
        self.cache_latents = cache_latents
        self.cache_latents_to_disk = cache_latents_to_disk
        self.validation_prompt = validation_prompt
        self.validation_steps = validation_steps
        self.validation_images = validation_images
        self.output_dir = output_dir
        self.save_every_n_steps = save_every_n_steps
        self.save_precision = save_precision
        self.gpu_type = gpu_type
        self.num_gpus = num_gpus

    def to_kohya_args(self) -> list[str]:
        """Convert to kohya-ss/sd-scripts command line arguments."""
        args = [
            f"--pretrained_model_name_or_path={self.base_model}",
            f"--train_data_dir={self.dataset_dir}",
            f"--resolution={self.resolution}",
            f"--train_batch_size={self.batch_size}",
            f"--max_train_steps={self.max_train_steps}",
            f"--learning_rate={self.learning_rate}",
            f"--lr_scheduler={self.lr_scheduler}",
            f"--lr_warmup_steps={self.lr_warmup_steps}",
            f"--optimizer_type={self.optimizer}",
            f"--mixed_precision={self.mixed_precision}",
            f"--gradient_accumulation_steps={self.gradient_accumulation_steps}",
            f"--network_module={self.network_module}",
            f"--network_dim={self.network_dim}",
            f"--network_alpha={self.lora_alpha}",
            f"--network_dropout={self.lora_dropout}",
            f"--output_dir={self.output_dir}",
            f"--save_every_n_steps={self.save_every_n_steps}",
            f"--save_precision={self.save_precision}",
        ]

        if self.noise_offset > 0:
            args.append(f"--noise_offset={self.noise_offset}")
        if self.min_snr_gamma > 0:
            args.append(f"--min_snr_gamma={self.min_snr_gamma}")
        if self.scale_lr:
            args.append("--scale_lr")
        if self.cache_latents:
            args.append("--cache_latents")
        if self.cache_latents_to_disk:
            args.append("--cache_latents_to_disk")

        if self.validation_prompt:
            args.append(f"--validation_prompt={self.validation_prompt}")
        if self.validation_steps > 0:
            args.append(f"--validation_steps={self.validation_steps}")

        return args


# ════════════════════════════════════════════════════════════════════════════
# TRAINING JOB
# ════════════════════════════════════════════════════════════════════════════

class LoRATrainingJob:
    """Represents a LoRA training job."""

    def __init__(
        self,
        job_id: str,
        character_id: str,
        project_id: str,
        config: LoRATrainingConfig,
        backend: TrainingBackend = TrainingBackend.MODAL,
    ):
        self.job_id = job_id
        self.character_id = character_id
        self.project_id = project_id
        self.config = config
        self.backend = backend
        self.status = TrainingStatus.PENDING
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.external_id: Optional[str] = None  # Modal/RunPod job ID
        self.logs: list[str] = []
        self.progress: float = 0.0
        self.current_step: int = 0
        self.lora_path: Optional[str] = None
        self.error_message: Optional[str] = None

    def add_log(self, message: str):
        self.logs.append(f"[{datetime.utcnow().isoformat()}] {message}")

    def update_progress(self, step: int, total: int, message: str = ""):
        self.current_step = step
        self.progress = min(1.0, step / total if total > 0 else 0)
        if message:
            self.add_log(message)


# ════════════════════════════════════════════════════════════════════════════
# TRAINER BASE
# ════════════════════════════════════════════════════════════════════════════

class BaseLoRATrainer:
    """Base class for LoRA training backends."""

    def __init__(self):
        pass

    async def submit(self, job: LoRATrainingJob) -> str:
        """Submit job, return external job ID."""
        raise NotImplementedError

    async def get_status(self, job: LoRATrainingJob) -> TrainingStatus:
        """Get current job status."""
        raise NotImplementedError

    async def get_logs(self, job: LoRATrainingJob) -> list[str]:
        """Get job logs."""
        raise NotImplementedError

    async def cancel(self, job: LoRATrainingJob) -> bool:
        """Cancel job."""
        raise NotImplementedError

    async def download_lora(self, job: LoRATrainingJob, local_path: Path) -> bool:
        """Download trained LoRA weights."""
        raise NotImplementedError


# ════════════════════════════════════════════════════════════════════════════
# MODAL TRAINER
# ════════════════════════════════════════════════════════════════════════════

class ModalLoRATrainer(BaseLoRATrainer):
    """LoRA training on Modal (modal.com)."""

    def __init__(self, token_id: str = "", token_secret: str = ""):
        super().__init__()
        self.token_id = token_id or os.getenv("MODAL_TOKEN_ID", "")
        self.token_secret = token_secret or os.getenv("MODAL_TOKEN_SECRET", "")
        self.base_url = "https://api.modal.com/v1"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            auth = aiohttp.BasicAuth(self.token_id, self.token_secret)
            self._session = aiohttp.ClientSession(
                auth=auth,
                headers={"Content-Type": "application/json"},
            )
        return self._session

    async def submit(self, job: LoRATrainingJob) -> str:
        """Submit training job to Modal."""
        session = await self._get_session()

        # Prepare Modal function call payload
        payload = {
            "function_name": "train_lora",
            "args": [],
            "kwargs": {
                "config": job.config.to_kohya_args(),
                "character_id": job.character_id,
                "project_id": job.project_id,
            },
        }

        url = f"{self.base_url}/functions/call"
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Modal submit failed: {text}")

            data = await resp.json()
            function_call_id = data.get("function_call_id")
            if not function_call_id:
                raise RuntimeError("No function_call_id returned")

            job.external_id = function_call_id
            job.status = TrainingStatus.QUEUED
            job.add_log(f"Submitted to Modal: {function_call_id}")
            return function_call_id

    async def get_status(self, job: LoRATrainingJob) -> TrainingStatus:
        if not job.external_id:
            return job.status

        session = await self._get_session()
        url = f"{self.base_url}/function-calls/{job.external_id}"

        async with session.get(url) as resp:
            if resp.status != 200:
                return TrainingStatus.FAILED

            data = await resp.json()
            status = data.get("status", "unknown")

            # Map Modal status to our status
            status_map = {
                "pending": TrainingStatus.QUEUED,
                "running": TrainingStatus.RUNNING,
                "success": TrainingStatus.COMPLETED,
                "failure": TrainingStatus.FAILED,
            }

            return status_map.get(status, TrainingStatus.FAILED)

    async def get_logs(self, job: LoRATrainingJob) -> list[str]:
        if not job.external_id:
            return job.logs

        session = await self._get_session()
        url = f"{self.base_url}/function-calls/{job.external_id}/logs"

        async with session.get(url) as resp:
            if resp.status != 200:
                return job.logs

            data = await resp.json()
            logs = data.get("logs", [])
            return [log.get("message", "") for log in logs]

    async def cancel(self, job: LoRATrainingJob) -> bool:
        if not job.external_id:
            return False

        session = await self._get_session()
        url = f"{self.base_url}/function-calls/{job.external_id}/cancel"

        async with session.post(url) as resp:
            return resp.status == 200

    async def download_lora(self, job: LoRATrainingJob, local_path: Path) -> bool:
        # Modal would need a separate endpoint for artifact download
        # For now, return False - implement based on Modal's artifact API
        return False


# ════════════════════════════════════════════════════════════════════════════
# RUNPOD TRAINER
# ════════════════════════════════════════════════════════════════════════════

class RunPodLoRATrainer(BaseLoRATrainer):
    """LoRA training on RunPod."""

    def __init__(self, api_key: str = "", endpoint_id: str = ""):
        super().__init__()
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY", "")
        self.endpoint_id = endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID", "")
        self.base_url = "https://api.runpod.ai/v2"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._session

    async def submit(self, job: LoRATrainingJob) -> str:
        session = await self._get_session()

        payload = {
            "input": {
                "config": job.config.to_kohya_args(),
                "character_id": job.character_id,
                "project_id": job.project_id,
            }
        }

        url = f"{self.base_url}/{self.endpoint_id}/run"
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"RunPod submit failed: {text}")

            data = await resp.json()
            run_id = data.get("id")
            if not run_id:
                raise RuntimeError("No run ID returned")

            job.external_id = run_id
            job.status = TrainingStatus.QUEUED
            job.add_log(f"Submitted to RunPod: {run_id}")
            return run_id

    async def get_status(self, job: LoRATrainingJob) -> TrainingStatus:
        if not job.external_id:
            return job.status

        session = await self._get_session()
        url = f"{self.base_url}/{self.endpoint_id}/status/{job.external_id}"

        async with session.get(url) as resp:
            if resp.status != 200:
                return TrainingStatus.FAILED

            data = await resp.json()
            status = data.get("status", "unknown")

            status_map = {
                "IN_QUEUE": TrainingStatus.QUEUED,
                "IN_PROGRESS": TrainingStatus.RUNNING,
                "COMPLETED": TrainingStatus.COMPLETED,
                "FAILED": TrainingStatus.FAILED,
            }

            return status_map.get(status, TrainingStatus.FAILED)

    async def get_logs(self, job: LoRATrainingJob) -> list[str]:
        if not job.external_id:
            return job.logs

        session = await self._get_session()
        url = f"{self.base_url}/{self.endpoint_id}/logs/{job.external_id}"

        async with session.get(url) as resp:
            if resp.status != 200:
                return job.logs

            data = await resp.json()
            return data.get("logs", [])

    async def cancel(self, job: LoRATrainingJob) -> bool:
        if not job.external_id:
            return False

        session = await self._get_session()
        url = f"{self.base_url}/{self.endpoint_id}/cancel/{job.external_id}"

        async with session.post(url) as resp:
            return resp.status == 200

    async def download_lora(self, job: LoRATrainingJob, local_path: Path) -> bool:
        # RunPod artifact download
        if not job.external_id:
            return False

        session = await self._get_session()
        url = f"{self.base_url}/{self.endpoint_id}/artifacts/{job.external_id}"

        async with session.get(url) as resp:
            if resp.status != 200:
                return False

            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)
            return True


# ════════════════════════════════════════════════════════════════════════════
# LOCAL TRAINER (fallback)
# ════════════════════════════════════════════════════════════════════════════

class LocalLoRATrainer(BaseLoRATrainer):
    """Local LoRA training (requires GPU)."""

    def __init__(self):
        super().__init__()
        self.process: Optional[asyncio.subprocess.Process] = None

    async def submit(self, job: LoRATrainingJob) -> str:
        # Build command
        args = [
            "accelerate", "launch",
            "--num_cpu_threads_per_process=4",
            "sd-scripts/train_network.py",
            *job.config.to_kohya_args(),
        ]

        job.add_log(f"Starting local training: {' '.join(args)}")
        job.status = TrainingStatus.RUNNING
        job.started_at = datetime.utcnow()

        # Start process
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        job.external_id = str(self.process.pid)
        job.add_log(f"Training started (PID: {self.process.pid})")

        # Monitor in background
        asyncio.create_task(self._monitor_process(job))

        return str(self.process.pid)

    async def _monitor_process(self, job: LoRATrainingJob):
        if not self.process:
            return

        try:
            async for line in self.process.stdout:
                decoded = line.decode().strip()
                if decoded:
                    job.add_log(decoded)

                    # Parse progress from kohya output
                    if "epoch" in decoded.lower() and "step" in decoded.lower():
                        # Parse step info
                        pass

            await self.process.wait()

            if self.process.returncode == 0:
                job.status = TrainingStatus.COMPLETED
                job.add_log("Training completed successfully")

                # Find output LoRA
                output_dir = Path(job.config.output_dir)
                lora_files = list(output_dir.glob("*.safetensors"))
                if lora_files:
                    latest = max(lora_files, key=lambda f: f.stat().st_mtime)
                    job.lora_path = str(latest)
                    job.add_log(f"LoRA saved to: {job.lora_path}")
            else:
                job.status = TrainingStatus.FAILED
                job.error_message = f"Training failed with code {self.process.returncode}"
                job.add_log(f"Training failed: {job.error_message}")

        except Exception as e:
            job.status = TrainingStatus.FAILED
            job.error_message = str(e)
            job.add_log(f"Training error: {e}")
        finally:
            job.completed_at = datetime.utcnow()

    async def get_status(self, job: LoRATrainingJob) -> TrainingStatus:
        return job.status

    async def get_logs(self, job: LoRATrainingJob) -> list[str]:
        return job.logs

    async def cancel(self, job: LoRATrainingJob) -> bool:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            job.status = TrainingStatus.CANCELLED
            job.add_log("Training cancelled")
            return True
        return False

    async def download_lora(self, job: LoRATrainingJob, local_path: Path) -> bool:
        if job.lora_path and Path(job.lora_path).exists():
            import shutil
            shutil.copy2(job.lora_path, local_path)
            return True
        return False


# ════════════════════════════════════════════════════════════════════════════
# TRAINER REGISTRY
# ════════════════════════════════════════════════════════════════════════════

_TRAINERS: dict[TrainingBackend, BaseLoRATrainer] = {}


def get_trainer(backend: TrainingBackend) -> BaseLoRATrainer:
    """Get or create trainer for backend."""
    if backend not in _TRAINERS:
        if backend == TrainingBackend.MODAL:
            _TRAINERS[backend] = ModalLoRATrainer()
        elif backend == TrainingBackend.RUNPOD:
            _TRAINERS[backend] = RunPodLoRATrainer()
        elif backend == TrainingBackend.LOCAL:
            _TRAINERS[backend] = LocalLoRATrainer()
        else:
            raise ValueError(f"Unsupported backend: {backend}")
    return _TRAINERS[backend]


async def submit_lora_training(
    character_id: str,
    project_id: str,
    config: LoRATrainingConfig,
    backend: TrainingBackend = TrainingBackend.MODAL,
) -> LoRATrainingJob:
    """Convenience function to submit a LoRA training job."""
    job_id = str(uuid.uuid4())[:8]
    job = LoRATrainingJob(
        job_id=job_id,
        character_id=character_id,
        project_id=project_id,
        config=config,
        backend=backend,
    )

    trainer = get_trainer(backend)
    await trainer.submit(job)

    return job


async def get_training_status(job: LoRATrainingJob) -> TrainingStatus:
    """Get status of a training job."""
    trainer = get_trainer(job.backend)
    return await trainer.get_status(job)


async def cancel_training(job: LoRATrainingJob) -> bool:
    """Cancel a training job."""
    trainer = get_trainer(job.backend)
    return await trainer.cancel(job)


async def download_lora(job: LoRATrainingJob, local_path: Path) -> bool:
    """Download trained LoRA weights."""
    trainer = get_trainer(job.backend)
    return await trainer.download_lora(job, local_path)