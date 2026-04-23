"""
Gateway HTTP Service — FastAPI + Operator Web UI

提供：
- REST API：任务管理（创建/查询/恢复/中止）
- SSE：任务实时进度推送
- Web UI：可视化 Operator 控制台

端口：8765
静态文件：ui/operator-ui/dist/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import sse_starlette
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.requests import Request
from starlette.responses import Response

# ── Project Paths ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gateway")

# ── Type Imports ───────────────────────────────────────────────────────────────

from providers.base import RunState, TaskPhase, TaskOutput
from runtimes.checkpoint_store import CheckpointStore, CheckpointRecord

# ── Lazy Imports（避免循环导入）────────────────────────────────────────────────

def _get_adaptive_runtime():
    from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig
    return AdaptiveRuntime, PipelineConfig

def _get_feishu_adapter():
    from channels import FeishuAdapter, FeishuConfig, register_feishu_webhook
    return FeishuAdapter, FeishuConfig, register_feishu_webhook

# ── SSE Event Queues ───────────────────────────────────────────────────────────

# job_id → asyncio.Queue for SSE subscribers
_sse_queues: Dict[str, asyncio.Queue] = {}
_sse_queues_lock = asyncio.Lock()


async def _publish_event(job_id: str, event: Dict[str, Any]) -> None:
    """Publish an SSE event to all subscribers of a job."""
    async with _sse_queues_lock:
        queue = _sse_queues.get(job_id)
    if queue is not None:
        await queue.put(json.dumps(event, ensure_ascii=False))


# ── App Factory ───────────────────────────────────────────────────────────────

def create_app(
    checkpoint_store: Optional[CheckpointStore] = None,
    ui_dir: Optional[Path] = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Curriculum-Forge Gateway",
        description="MoonClaw-style agent runtime API + Operator Web UI",
        version="0.1.0",
    )

    # ── State ────────────────────────────────────────────────────────────────

    app.state.store = checkpoint_store or CheckpointStore()
    app.state.ui_dir = ui_dir or (PROJECT_ROOT / "ui" / "operator-ui" / "dist")
    app.state._running_jobs: Dict[str, asyncio.Task] = {}

    # ── CORS ────────────────────────────────────────────────────────────────

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── SSE Helpers ─────────────────────────────────────────────────────────

    async def event_generator(job_id: str):
        """Yield SSE events for a job until it completes or subscriber leaves."""
        queue: asyncio.Queue = asyncio.Queue()

        # Register queue
        async with _sse_queues_lock:
            _sse_queues[job_id] = queue

        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=60.0)
                    yield sse_starlette.SSEEvent(data=data)
                except asyncio.TimeoutError:
                    # Keepalive heartbeat
                    yield sse_starlette.SSEEvent(data=": keepalive\n\n")
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            # Unregister queue
            async with _sse_queues_lock:
                if _sse_queues.get(job_id) is queue:
                    del _sse_queues[job_id]

    # ── Routes ─────────────────────────────────────────────────────────────

    # Health check
    @app.get("/health", tags=["system"])
    async def health():
        return {
            "status": "healthy",
            "version": "0.1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Jobs API ─────────────────────────────────────────────────────────────

    @app.get("/jobs", tags=["jobs"])
    async def list_jobs(
        profile: Optional[str] = Query(None, description="Filter by profile"),
        state: Optional[str] = Query(
            None, description="Filter by state (PENDING/RUNNING/COMPLETED/FAILED)"
        ),
        limit: int = Query(50, ge=1, le=500),
    ):
        """List all checkpoint records."""
        store = app.state.store
        run_state = None
        if state:
            try:
                run_state = RunState(state)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid state: {state}. Valid: {[s.value for s in RunState]}",
                )
        records = store.list(profile=profile, state=run_state, limit=limit)
        return {
            "jobs": [_record_to_api(r) for r in records],
            "total": len(records),
        }

    @app.post("/jobs", tags=["jobs"], status_code=201)
    async def create_job(request: Request):
        """
        Create a new job from a profile or proposal.

        Body:
            profile (str): Profile name from profiles/ directory
            config (dict, optional): Runtime config overrides
            proposal (dict, optional): Full proposal payload (takes precedence)
        """
        body = await request.json()
        store = app.state.store

        # ── Path 1: Proposal payload ────────────────────────────────────────
        if "proposal" in body:
            proposal = body["proposal"]
            run_id = store.new_id()
            record = CheckpointRecord(
                id=run_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                profile=proposal.get("profile", "unknown"),
                phase=TaskPhase.CURRICULUM.value,
                state=RunState.PENDING,
                config=proposal.get("config", {}),
                state_data=proposal,
                metrics={},
                description=proposal.get("description", ""),
            )
            store.save(record)
            return {"job": _record_to_api(record), "created": True}

        # ── Path 2: Profile name ────────────────────────────────────────────
        profile_name = body.get("profile")
        if not profile_name:
            raise HTTPException(
                status_code=400, detail="Either 'profile' or 'proposal' is required"
            )

        profile_path = PROJECT_ROOT / "profiles" / f"{profile_name}.json"
        if not profile_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Profile '{profile_name}' not found at {profile_path}",
            )

        with open(profile_path, encoding="utf-8") as f:
            config = json.load(f)

        run_id = store.new_id()
        record = CheckpointRecord(
            id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            profile=profile_name,
            phase=TaskPhase.CURRICULUM.value,
            state=RunState.PENDING,
            config=config,
            state_data={},
            metrics={},
            description=body.get("description", f"Job from profile '{profile_name}'"),
        )
        store.save(record)
        return {"job": _record_to_api(record), "created": True}

    @app.get("/jobs/{job_id}", tags=["jobs"])
    async def get_job(job_id: str):
        """Get a single job's full details."""
        store = app.state.store
        record = store.load(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        return _record_to_api(record, include_state_data=True)

    @app.post("/jobs/{job_id}/resume", tags=["jobs"])
    async def resume_job(job_id: str, background_tasks: BackgroundTasks):
        """Resume a failed/pending job."""
        store = app.state.store
        record = store.load(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

        if record.state == RunState.RUNNING:
            raise HTTPException(
                status_code=409, detail="Job is already running"
            )

        # Update state
        record.state = RunState.RUNNING
        record.updated_at = datetime.now(timezone.utc).isoformat()
        store.save(record)

        # Run in background
        task = asyncio.create_task(_run_job_background(job_id, app))
        app.state._running_jobs[job_id] = task

        return {"job": _record_to_api(record), "resumed": True}

    @app.post("/jobs/{job_id}/abort", tags=["jobs"])
    async def abort_job(job_id: str):
        """Abort a running job."""
        store = app.state.store
        record = store.load(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

        # Cancel background task if running
        task = app.state._running_jobs.get(job_id)
        if task:
            task.cancel()
            del app.state._running_jobs[job_id]

        record.state = RunState.FAILED
        record.finished_at = datetime.now(timezone.utc).isoformat()
        store.save(record)

        await _publish_event(job_id, {"event": "abort", "job_id": job_id})

        return {"job": _record_to_api(record), "aborted": True}

    @app.get("/jobs/{job_id}/stream", tags=["jobs"])
    async def stream_job(job_id: str):
        """SSE stream for real-time job updates."""
        store = app.state.store
        record = store.load(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

        return event_generator(job_id)

    # ── Profiles API ─────────────────────────────────────────────────────────

    @app.get("/profiles", tags=["profiles"])
    async def list_profiles():
        """List available profiles."""
        profiles_dir = PROJECT_ROOT / "profiles"
        profiles_dir.mkdir(exist_ok=True)
        profiles = []
        for p in sorted(profiles_dir.glob("*.json")):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            profiles.append({
                "name": p.stem,
                "file": p.name,
                "description": data.get("description", ""),
            })
        return {"profiles": profiles}

    # ── Store Summary ────────────────────────────────────────────────────────

    @app.get("/stats", tags=["system"])
    async def stats():
        """Gateway statistics."""
        store = app.state.store
        return store.summary()

    # ── Static UI ────────────────────────────────────────────────────────────

    @app.get("/", include_in_schema=False)
    async def serve_index():
        ui_index = app.state.ui_dir / "index.html"
        if ui_index.exists():
            return FileResponse(str(ui_index))
        return HTMLResponse(
            "<html><body><h1>Curriculum-Forge Gateway</h1>"
            "<p>UI not built yet. Use the API at <a href='/docs'>/docs</a>.</p>"
            "</body></html>"
        )

    @app.get("/ui/{path:path}", include_in_schema=False)
    async def serve_ui(path: str):
        file_path = app.state.ui_dir / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return HTMLResponse("Not found", status_code=404)

    return app


# ── Background Job Runner ─────────────────────────────────────────────────────

async def _run_job_background(job_id: str, app: FastAPI) -> None:
    """Run a job in the background, publishing SSE events."""
    store = app.state.store
    record = store.load(job_id)
    if record is None:
        return

    try:
        AdaptiveRuntime, PipelineConfig = _get_adaptive_runtime()

        # Build config from stored profile
        config = PipelineConfig(
            profile_name=record.profile,
            max_iterations=record.config.get("max_iterations", 10),
        )

        runtime = AdaptiveRuntime(config=config, checkpoint_store=store)

        async for event in runtime.run_stream(record.id):
            # Persist updated record
            updated = store.load(job_id)
            if updated:
                await _publish_event(job_id, {
                    "event": "update",
                    "job": _record_to_api(updated),
                })

            # Check for completion
            updated = store.load(job_id)
            if updated and updated.state in (RunState.COMPLETED, RunState.FAILED):
                await _publish_event(job_id, {
                    "event": "done",
                    "state": updated.state.value,
                })
                break

    except asyncio.CancelledError:
        logger.info(f"[{job_id}] Job cancelled")
        await _publish_event(job_id, {"event": "cancelled"})
    except Exception as exc:
        logger.exception(f"[{job_id}] Job failed: {exc}")
        # Mark record as failed
        record = store.load(job_id)
        if record:
            record.state = RunState.FAILED
            record.finished_at = datetime.now(timezone.utc).isoformat()
            store.save(record)
        await _publish_event(job_id, {"event": "error", "error": str(exc)})
    finally:
        # Cleanup
        if job_id in app.state._running_jobs:
            del app.state._running_jobs[job_id]


# ── Serialization Helpers ─────────────────────────────────────────────────────

def _record_to_api(record: CheckpointRecord, include_state_data: bool = False) -> Dict[str, Any]:
    """Convert CheckpointRecord to API response dict."""
    phases = {}
    for phase in TaskPhase:
        phase_key = phase.value
        phase_data = record.state_data.get(phase_key, {})
        phases[phase_key] = {
            "status": phase_data.get("status", "pending"),
            "output": phase_data.get("output") if include_state_data else None,
        }

    result = {
        "id": record.id,
        "profile": record.profile,
        "description": record.description,
        "status": record.state.value,
        "current_phase": record.phase,
        "phases": phases,
        "created_at": record.created_at,
        "updated_at": getattr(record, "updated_at", record.created_at),
        "finished_at": record.finished_at,
        "metrics": record.metrics,
    }
    if include_state_data:
        result["config"] = record.config
        result["state_data"] = record.state_data
    return result


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, uvicorn

    parser = argparse.ArgumentParser(description="Curriculum-Forge Gateway")
    parser.add_argument(
        "--port", type=int, default=8765, help="Port to listen on (default: 8765)"
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload"
    )
    args = parser.parse_args()

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


# ── Feishu Webhook Integration ────────────────────────────────────────────────

def setup_feishu_webhook(
    app: FastAPI,
    app_id: str,
    app_secret: str,
    encrypt_key: str = "",
    verification_token: str = "",
    webhook_path: str = "/webhooks/feishu",
    on_message: Optional[callable] = None,
) -> "FeishuAdapter":
    """
    在 FastAPI 应用中注册飞书 Webhook
    
    Args:
        app: FastAPI 应用实例
        app_id: 飞书应用 ID
        app_secret: 飞书应用密钥
        encrypt_key: 事件加密密钥（可选）
        verification_token: 事件验证 token（可选）
        webhook_path: Webhook 路径
        on_message: 消息回调函数
    
    Returns:
        FeishuAdapter 实例
    """
    FeishuAdapter, FeishuConfig, register_feishu_webhook = _get_feishu_adapter()
    
    config = FeishuConfig(
        app_id=app_id,
        app_secret=app_secret,
        encrypt_key=encrypt_key,
        verification_token=verification_token,
    )
    
    adapter = FeishuAdapter(config=config, on_message=on_message)
    
    # 注册 webhook 路由
    register_feishu_webhook(app, adapter, path=webhook_path)
    
    # 存储到 app.state
    app.state.feishu_adapter = adapter
    
    logger.info(f"飞书 Webhook 已注册: {webhook_path}")
    return adapter
