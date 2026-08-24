"""
Model Registry — Stores and manages trained LoRA weights.

Supports local storage, S3, and cloud storage backends.
Injects LoRA paths into visual providers at generation time.
"""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ModelRegistryError(Exception):
    pass


class LoRAModel:
    """Represents a trained LoRA model."""

    def __init__(
        self,
        model_id: str,
        character_id: str,
        character_name: str,
        project_id: str,
        lora_path: Path,
        training_job_id: str,
        config: dict[str, Any],  # TrainingConfig
        metadata: Optional[dict[str, Any]] = None,
    ):
        self.model_id = model_id
        self.character_id = character_id
        self.character_name = character_name
        self.project_id = project_id
        self.lora_path = lora_path
        self.training_job_id = training_job_id
        self.config = config
        self.metadata = metadata or {}

        self.created_at = datetime.utcnow()
        self.file_size = lora_path.stat().st_size if lora_path.exists() else 0
        self.checksum = self._compute_checksum(lora_path) if lora_path.exists() else ""
        self.is_active = True

    def _compute_checksum(self, path: Path) -> str:
        """Compute SHA256 checksum of LoRA file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "character_id": self.character_id,
            "character_name": self.character_name,
            "project_id": self.project_id,
            "lora_path": str(self.lora_path),
            "training_job_id": self.training_job_id,
            "config": self.config,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "file_size": self.file_size,
            "checksum": self.checksum,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoRAModel":
        model = cls(
            model_id=data["model_id"],
            character_id=data["character_id"],
            character_name=data["character_name"],
            project_id=data["project_id"],
            lora_path=Path(data["lora_path"]),
            training_job_id=data["training_job_id"],
            config=data["config"],
            metadata=data.get("metadata", {}),
        )
        model.created_at = datetime.fromisoformat(data["created_at"])
        model.file_size = data.get("file_size", 0)
        model.checksum = data.get("checksum", "")
        model.is_active = data.get("is_active", True)
        return model


class ModelRegistry:
    """
    Registry for trained LoRA models.
    
    Supports multiple storage backends:
    - Local filesystem (default)
    - S3-compatible (MinIO, AWS S3, etc.)
    - Cloud storage (GCS, Azure Blob)
    """

    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path(os.getenv("LORA_STORAGE_PATH", "./loras"))
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.registry_file = self.base_path / "registry.json"
        self.models_dir = self.base_path / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self._models: dict[str, LoRAModel] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load registry from disk."""
        if self.registry_file.exists():
            try:
                data = json.loads(self.registry_file.read_text())
                for model_data in data.get("models", []):
                    model = LoRAModel.from_dict(model_data)
                    self._models[model.model_id] = model
                logger.info(f"Loaded {len(self._models)} LoRA models from registry")
            except Exception as e:
                logger.error(f"Failed to load model registry: {e}")

    def _save_registry(self) -> None:
        """Save registry to disk."""
        try:
            data = {
                "version": 1,
                "updated_at": datetime.utcnow().isoformat(),
                "models": [m.to_dict() for m in self._models.values()],
            }
            self.registry_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save model registry: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # CRUD OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    def register(
        self,
        character_id: str,
        character_name: str,
        project_id: str,
        lora_path: Path,
        training_job_id: str,
        config: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> LoRAModel:
        """Register a new LoRA model from a completed training job."""
        model_id = f"lora_{character_id}_{int(datetime.utcnow().timestamp())}"

        # Copy to registry
        registry_path = self.models_dir / f"{model_id}.safetensors"
        shutil.copy2(lora_path, registry_path)

        model = LoRAModel(
            model_id=model_id,
            character_id=character_id,
            character_name=character_name,
            project_id=project_id,
            lora_path=registry_path,
            training_job_id=training_job_id,
            config=config,
            metadata=metadata,
        )

        self._models[model_id] = model
        self._save_registry()

        logger.info(f"Registered LoRA model: {model_id} for character {character_name}")
        return model

    def get(self, model_id: str) -> Optional[LoRAModel]:
        """Get model by ID."""
        return self._models.get(model_id)

    def get_by_character(self, character_id: str) -> list[LoRAModel]:
        """Get all models for a character."""
        return [m for m in self._models.values() if m.character_id == character_id]

    def get_by_project(self, project_id: str) -> list[LoRAModel]:
        """Get all models for a project."""
        return [m for m in self._models.values() if m.project_id == project_id]

    def list_all(self, active_only: bool = True) -> list[LoRAModel]:
        """List all models."""
        models = list(self._models.values())
        if active_only:
            models = [m for m in models if m.is_active]
        return sorted(models, key=lambda m: m.created_at, reverse=True)

    def update(self, model_id: str, **kwargs) -> Optional[LoRAModel]:
        """Update model metadata."""
        model = self._models.get(model_id)
        if not model:
            return None

        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)

        self._save_registry()
        return model

    def deactivate(self, model_id: str) -> bool:
        """Soft delete a model."""
        model = self._models.get(model_id)
        if not model:
            return False

        model.is_active = False
        self._save_registry()
        return True

    def delete(self, model_id: str, delete_file: bool = False) -> bool:
        """Hard delete a model."""
        model = self._models.get(model_id)
        if not model:
            return False

        if delete_file and model.lora_path.exists():
            model.lora_path.unlink()

        del self._models[model_id]
        self._save_registry()
        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # PROVIDER INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════════

    def get_lora_for_character(
        self,
        character_id: str,
        project_id: str = None,
    ) -> Optional[tuple[str, float]]:
        """
        Get the best LoRA for a character.
        
        Returns (lora_path, lora_scale) or None if no model.
        """
        models = self.get_by_character(character_id)
        if project_id:
            models = [m for m in models if m.project_id == project_id]

        # Filter active
        models = [m for m in models if m.is_active and m.lora_path.exists()]

        if not models:
            return None

        # Use most recent active model
        best = max(models, key=lambda m: m.created_at)

        # Default scale from config, or 1.0
        scale = best.config.get("lora_scale", 1.0)

        return (str(best.lora_path), scale)

    def get_all_for_prompt(
        self,
        character_ids: list[str],
        project_id: str = None,
    ) -> dict[str, tuple[str, float]]:
        """Get LoRAs for multiple characters for prompt injection."""
        result = {}
        for char_id in character_ids:
            lora = self.get_lora_for_character(char_id, project_id)
            if lora:
                result[char_id] = lora
        return result


# Global registry instance
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry