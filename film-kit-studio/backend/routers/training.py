"""
Training Router — API endpoints for LoRA training and dataset curation.
"""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field

from config import settings
from database import get_session
from models import Character, Project
from services.training import (
    LoRATrainingConfig,
    TrainingBackend,
    TrainingStatus,
    submit_lora_training,
    get_training_status,
    cancel_training,
    download_lora,
    DatasetCurator,
    get_model_registry,
    LoRATrainingJob,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/training", tags=["training"])

logger = logging.getLogger(__name__)

# In-memory job store
_training_jobs: dict[str, LoRATrainingJob] = {}


# ════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════

class TrainingConfigRequest(BaseModel):
    """Training configuration (matches LoRATrainingConfig)."""
    base_model: str = "stabilityai/stable-diffusion-xl-base-1.0"
    model_type: str = "sdxl"
    resolution: int = 512
    batch_size: int = 1
    lora_rank: int = 32
    lora_alpha: int = 32
    lora_dropout: float = 0.0
    max_train_steps: int = 1000
    learning_rate: float = 1e-4
    lr_scheduler: str = "cosine_with_restarts"
    lr_warmup_steps: int = 100
    optimizer: str = "AdamW8bit"
    mixed_precision: str = "fp16"
    gradient_accumulation_steps: int = 1
    gpu_type: str = "A100-40GB"
    num_gpus: int = 1
    output_dir: str = "./loras"
    save_every_n_steps: int = 500
    save_precision: str = "fp16"


class StartTrainingRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    character_id: str = Field(..., description="Character ID to train")
    config: Optional[TrainingConfigRequest] = None
    backend: str = Field("modal", description="Training backend: modal, runpod, local")
    dataset_video_paths: list[str] = Field(default_factory=list, description="Paths to video clips for keyframe extraction")
    dataset_reference_images: list[str] = Field(default_factory=list, description="Paths to reference images")
    target_dataset_size: int = Field(50, ge=10, le=200)


class TrainingJobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class TrainingJobStatus(BaseModel):
    job_id: str
    character_id: str
    project_id: str
    status: str
    progress: float
    current_step: int
    max_steps: int
    logs: list[str]
    lora_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class CurateDatasetRequest(BaseModel):
    project_id: str
    character_id: str
    video_paths: list[str] = Field(default_factory=list)
    reference_images: list[str] = Field(default_factory=list)
    target_count: int = 50
    caption_template: str = "{character}, {description}"


class ModelRegistryResponse(BaseModel):
    model_id: str
    character_id: str
    character_name: str
    project_id: str
    lora_path: str
    created_at: str
    file_size: int
    checksum: str
    is_active: bool


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

async def _get_project(session: AsyncSession, project_id: str) -> Project:
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_character(session: AsyncSession, character_id: str) -> Character:
    stmt = select(Character).where(Character.id == character_id)
    result = await session.execute(stmt)
    character = result.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


def _config_to_dict(config: TrainingConfigRequest) -> dict:
    return config.dict()


# ════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@router.post("/lora/train", response_model=TrainingJobResponse)
async def start_lora_training(
    request: StartTrainingRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Start a LoRA training job for a character."""
    # Verify project and character
    await _get_project(session, request.project_id)
    character = await _get_character(session, request.character_id)

    # Build config
    config_dict = request.config.dict() if request.config else {}
    config = LoRATrainingConfig(**config_dict)

    # Try to use Modal if available
    backend = TrainingBackend.MODAL
    if request.backend == "runpod":
        backend = TrainingBackend.RUNPOD
    elif request.backend == "local":
        backend = TrainingBackend.LOCAL

    # Submit training job
    job = await submit_lora_training(
        character_id=request.character_id,
        project_id=request.project_id,
        config=config,
        backend=backend,
    )

    _training_jobs[job.job_id] = job

    return TrainingJobResponse(
        job_id=job.job_id,
        status=job.status.value,
        message="LoRA training job submitted",
    )


@router.get("/lora/{job_id}/status", response_model=TrainingJobStatus)
async def get_lora_training_status(job_id: str):
    """Get training job status."""
    job = _training_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    return TrainingJobStatus(
        job_id=job.job_id,
        character_id=job.character_id,
        project_id=job.project_id,
        status=job.status.value,
        progress=job.progress,
        current_step=job.current_step,
        max_steps=job.config.max_train_steps,
        logs=job.logs[-50:],  # Last 50 logs
        lora_path=job.lora_path,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.post("/lora/{job_id}/cancel")
async def cancel_lora_training(job_id: str):
    """Cancel a training job."""
    job = _training_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    if job.status in (TrainingStatus.COMPLETED, TrainingStatus.FAILED, TrainingStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Job already finished")

    success = await cancel_training(job)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel job")

    return {"message": "Training job cancelled", "job_id": job_id}


@router.get("/lora/{job_id}/download")
async def download_lora_weights(job_id: str):
    """Download trained LoRA weights."""
    job = _training_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    if not job.lora_path:
        raise HTTPException(status_code=404, detail="LoRA weights not available yet")

    from fastapi.responses import FileResponse
    path = Path(job.lora_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="LoRA file not found")

    return FileResponse(
        path=path,
        filename=f"lora_{job.character_id}.safetensors",
        media_type="application/octet-stream",
    )


@router.post("/dataset/curate")
async def curate_dataset(
    request: CurateDatasetRequest,
    session: AsyncSession = Depends(get_session),
):
    """Curate a training dataset from project assets."""
    await _get_project(session, request.project_id)
    character = await _get_character(session, request.character_id)

    project_dir = settings.projects_path / request.project_id
    curator = DatasetCurator(project_dir)

    video_paths = [Path(p) for p in request.video_paths if Path(p).exists()]
    reference_images = [Path(p) for p in request.reference_images if Path(p).exists()]

    result = curator.curate_from_project(
        character_name=character.name,
        video_paths=video_paths,
        reference_images=reference_images,
        target_count=request.target_count,
        caption_template=request.caption_template,
    )

    return {
        "dataset_dir": result["dataset_dir"],
        "image_count": result["image_count"],
        "metadata": result["metadata"],
    }


@router.get("/models", response_model=list[ModelRegistryResponse])
async def list_lora_models(
    project_id: Optional[str] = None,
    character_id: Optional[str] = None,
    active_only: bool = True,
):
    """List all registered LoRA models."""
    registry = get_model_registry()

    models = registry.list_all(active_only=active_only)

    if project_id:
        models = [m for m in models if m.project_id == project_id]
    if character_id:
        models = [m for m in models if m.character_id == character_id]

    return [
        ModelRegistryResponse(
            model_id=m.model_id,
            character_id=m.character_id,
            character_name=m.character_name,
            project_id=m.project_id,
            lora_path=str(m.lora_path),
            created_at=m.created_at.isoformat(),
            file_size=m.file_size,
            checksum=m.checksum,
            is_active=m.is_active,
        )
        for m in models
    ]


@router.get("/models/{model_id}")
async def get_lora_model(model_id: str):
    """Get a specific LoRA model."""
    registry = get_model_registry()
    model = registry.get(model_id)

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    return model.to_dict()


@router.get("/jobs", response_model=list[TrainingJobStatus])
async def list_training_jobs(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    character_id: Optional[str] = Query(None, description="Filter by character ID"),
    status: Optional[TrainingStatus] = Query(None, description="Filter by status"),
):
    """List all LoRA training jobs, optionally filtered."""
    jobs = list(_training_jobs.values())
    
    if project_id:
        jobs = [j for j in jobs if j.project_id == project_id]
    if character_id:
        jobs = [j for j in jobs if j.character_id == character_id]
    if status:
        jobs = [j for j in jobs if j.status == status]
    
    # Sort by created_at descending (newest first)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    
    return [job.to_dict() for job in jobs]


@router.post("/models/{model_id}/deactivate")
async def deactivate_lora_model(model_id: str):
    """Deactivate a LoRA model (soft delete)."""
    registry = get_model_registry()

    if not registry.deactivate(model_id):
        raise HTTPException(status_code=404, detail="Model not found")

    return {"message": "Model deactivated", "model_id": model_id}


@router.delete("/models/{model_id}")
async def delete_lora_model(
    model_id: str,
    delete_file: bool = Query(False, description="Also delete the LoRA file"),
):
    """Delete a LoRA model."""
    registry = get_model_registry()

    if not registry.delete(model_id, delete_file=delete_file):
        raise HTTPException(status_code=404, detail="Model not found")

    return {"message": "Model deleted", "model_id": model_id}


@router.get("/characters/{character_id}/lora")
async def get_character_lora(
    character_id: str,
    project_id: Optional[str] = None,
):
    """Get the best LoRA for a character."""
    registry = get_model_registry()
    result = registry.get_lora_for_character(character_id, project_id)

    if not result:
        raise HTTPException(status_code=404, detail="No LoRA found for character")

    lora_path, scale = result
    return {
        "character_id": character_id,
        "lora_path": lora_path,
        "lora_scale": scale,
    }