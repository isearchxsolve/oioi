"""
Background task manager for long-running pipeline operations.

Provides:
  - Task creation and tracking (stored in DB)
  - SSE (Server-Sent Events) streaming for real-time progress
  - Non-blocking execution via asyncio.create_task

Tasks are tracked in the Task table and also in an in-memory dict
for fast SSE polling without hitting the DB on every tick.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import Task

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Manages background tasks with progress tracking and SSE support.
    """

    def __init__(self):
        # task_id → asyncio.Queue for SSE events
        self._sse_queues: dict[str, asyncio.Queue] = {}
        # task_id → asyncio.Task
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def create_task(
        self,
        project_id: str,
        task_type: str,
    ) -> str:
        """Create a new task record in the DB and return its ID."""
        task_id = str(uuid.uuid4())

        async with async_session() as session:
            task = Task(
                id=task_id,
                project_id=project_id,
                task_type=task_type,
                status="pending",
                progress=0.0,
                message="Task created",
            )
            session.add(task)
            await session.commit()

        # Create SSE queue
        self._sse_queues[task_id] = asyncio.Queue()

        logger.info(f"Created task {task_id} (type={task_type}, project={project_id})")
        return task_id

    async def start_task(
        self,
        task_id: str,
        coro: Any,
    ) -> None:
        """Start a background task coroutine."""
        asyncio_task = asyncio.create_task(self._run_task(task_id, coro))
        self._running_tasks[task_id] = asyncio_task

    async def _run_task(self, task_id: str, coro: Any) -> None:
        """Wrapper that updates task status and emits SSE events."""
        await self._update_task(task_id, status="running", message="Task started")

        try:
            result = await coro
            await self._update_task(
                task_id,
                status="completed",
                progress=1.0,
                message="Task completed",
                result=result,
            )
            await self._emit_sse(task_id, "completed", {"result": result})

        except Exception as exc:
            logger.exception(f"Task {task_id} failed: {exc}")
            await self._update_task(
                task_id,
                status="failed",
                message=str(exc),
            )
            await self._emit_sse(task_id, "error", {"error": str(exc)})

        finally:
            # Signal end of SSE stream
            queue = self._sse_queues.get(task_id)
            if queue:
                await queue.put(None)
            self._running_tasks.pop(task_id, None)

    async def _update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> None:
        """Update task record in DB."""
        async with async_session() as session:
            stmt = select(Task).where(Task.id == task_id)
            result_db = await session.execute(stmt)
            task = result_db.scalar_one_or_none()
            if task:
                if status is not None:
                    task.status = status
                if progress is not None:
                    task.progress = progress
                if message is not None:
                    task.message = message
                if result is not None:
                    task.result = result
                task.updated_at = datetime.now(timezone.utc)
                await session.commit()

    async def update_progress(
        self,
        task_id: str,
        progress: float,
        message: str = "",
    ) -> None:
        """Update task progress (called by running tasks)."""
        await self._update_task(task_id, progress=progress, message=message)
        await self._emit_sse(task_id, "progress", {"progress": progress, "message": message})

    async def update_scene(
        self,
        task_id: str,
        scene_index: int,
        scene_status: str,
        message: str = "",
    ) -> None:
        """Emit a scene-level update event."""
        await self._emit_sse(task_id, "scene_update", {
            "scene_index": scene_index,
            "scene_status": scene_status,
            "message": message,
        })

    async def _emit_sse(self, task_id: str, event: str, data: dict) -> None:
        """Push an event to the SSE queue for this task."""
        queue = self._sse_queues.get(task_id)
        if queue:
            await queue.put({"event": event, "data": data})

    async def get_sse_stream(self, task_id: str):
        """
        Async generator that yields SSE events for a task.
        Used by the SSE endpoint.
        """
        queue = self._sse_queues.get(task_id)
        if queue is None:
            # Task may have already completed — check DB
            async with async_session() as session:
                stmt = select(Task).where(Task.id == task_id)
                result = await session.execute(stmt)
                task = result.scalar_one_or_none()
                if task:
                    yield {
                        "event": "progress",
                        "data": {"progress": task.progress, "message": task.message},
                    }
                    if task.status == "completed":
                        yield {"event": "completed", "data": {"result": task.result}}
                    elif task.status == "failed":
                        yield {"event": "error", "data": {"error": task.message}}
                return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                if event is None:
                    # End of stream
                    break
                yield event
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield {"event": "ping", "data": {}}

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task from the DB."""
        async with async_session() as session:
            stmt = select(Task).where(Task.id == task_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    def is_running(self, task_id: str) -> bool:
        """Check if a task is currently running."""
        task = self._running_tasks.get(task_id)
        return task is not None and not task.done()


# Global task manager instance
task_manager = TaskManager()
