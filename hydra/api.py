from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from hydra import __version__
from hydra.artifacts import ArtifactStore
from hydra.bootstrap import bootstrap_runtime
from hydra.budgets import BudgetExceeded, RequestBudget
from hydra.capture_uow import CaptureUnitOfWork
from hydra.code_agent import CodeAgent
from hydra.coding_request import CodingRequest, resolve_repository
from hydra.config import settings
from hydra.contracts import HydraTask
from hydra.kernel import HydraKernel
from hydra.learning_capture import LearningCapture
from hydra.model_scout import scan_models
from hydra.outbox_dispatcher import OutboxDispatcher
from hydra.outbox_worker import OutboxWorker
from hydra.provenance import ProvenanceLedger, ProvenanceRecord
from hydra.provider import LocalLLM
from hydra.rate_limit import RateLimit, SlidingWindowRateLimiter
from hydra.readiness import evaluate_readiness
from hydra.sandbox import OciSandbox
from hydra.security import SecurityConfig, require_admin_access, require_api_access
from hydra.security_audit import SecurityAudit
from hydra.translation import GlossaryStore, TranslationService
from hydra.workspaces import WorkspaceManager

llm = LocalLLM(settings.llm_url)
budget = RequestBudget(
    settings.max_input_chars,
    settings.max_output_tokens,
    settings.max_translation_chunks,
)
glossaries = GlossaryStore()
translations = TranslationService(llm, budget, glossaries)
artifacts = ArtifactStore()
provenance = ProvenanceLedger()
workspaces = WorkspaceManager(
    max_files=settings.workspace_max_files,
    max_bytes=settings.workspace_max_bytes,
)
learning = LearningCapture()
capture_uow = CaptureUnitOfWork(settings.runtime_db)
kernel = HydraKernel(capture_uow=capture_uow)
outbox_dispatcher = OutboxDispatcher(
    capture_uow.outbox,
    kernel.events,
    provenance,
    learning.corpus,
)
outbox_worker = OutboxWorker(capture_uow.outbox, outbox_dispatcher)
security_config = SecurityConfig(
    api_token=settings.api_token,
    admin_token=settings.admin_token,
)
rate_limiter = SlidingWindowRateLimiter()
security_audit = SecurityAudit(kernel.events)
api_rate_limit = RateLimit(
    requests=settings.api_rate_limit_per_minute,
    window_seconds=60,
)
admin_rate_limit = RateLimit(
    requests=settings.admin_rate_limit_per_minute,
    window_seconds=60,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.bootstrap = bootstrap_runtime(outbox_worker)
    worker_task = asyncio.create_task(outbox_worker.run_forever())
    app.state.outbox_worker_task = worker_task
    try:
        yield
    finally:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task


app = FastAPI(title="HYDRA-SO", version=__version__, lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    max_tokens: int = Field(default=1024, ge=1)


class TranslationRequest(BaseModel):
    text: str
    target_language: str
    source_language: str | None = None
    glossary_id: str | None = None


class GlossaryRequest(BaseModel):
    terms: dict[str, str] = Field(default_factory=dict)


@app.get("/health")
async def health() -> dict:
    return {"hydra": "ok", "version": __version__}


@app.get("/ready")
async def ready(response: Response) -> dict:
    llm_healthy = await llm.health()
    worker_task = getattr(app.state, "outbox_worker_task", None)
    worker_running = worker_task is not None and not worker_task.done()
    status = evaluate_readiness(
        outbox=capture_uow.outbox,
        events=kernel.events,
        provenance=provenance,
        llm_healthy=bool(llm_healthy),
        worker_running=worker_running,
        max_pending=settings.readiness_max_pending,
        max_oldest_pending_age_seconds=settings.readiness_max_pending_age_seconds,
    )
    if not status.ready:
        response.status_code = 503
    return {
        "ready": status.ready,
        "reasons": list(status.reasons),
        "pending_outbox": status.pending_outbox,
        "dead_letters": status.dead_letters,
        "events_integrity": status.events_integrity,
        "provenance_integrity": status.provenance_integrity,
        "llm_healthy": status.llm_healthy,
        "worker_running": status.worker_running,
        "oldest_pending_age_seconds": status.oldest_pending_age_seconds,
    }


@app.post("/v1/chat")
async def chat(req: ChatRequest, request: Request) -> dict:
    identity = require_api_access(request, security_config)
    rate_limiter.check(f"chat:{identity}", api_rate_limit)
    try:
        budget.validate_input(req.message)
        answer = await llm.chat(
            [{"role": "user", "content": req.message}],
            max_tokens=budget.output_tokens(req.max_tokens),
        )
        return {"answer": answer}
    except BudgetExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Local model unavailable") from exc


@app.post("/v1/translate")
async def translate(req: TranslationRequest, request: Request) -> dict:
    identity = require_api_access(request, security_config)
    rate_limiter.check(f"translate:{identity}", api_rate_limit)
    try:
        answer = await translations.translate(
            req.text, req.target_language, req.source_language, req.glossary_id
        )
        return {"translation": answer, "target_language": req.target_language}
    except BudgetExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Local model unavailable") from exc


@app.put("/v1/glossaries/{glossary_id}")
async def put_glossary(
    glossary_id: str,
    req: GlossaryRequest,
    request: Request,
) -> dict:
    identity = require_api_access(request, security_config)
    rate_limiter.check(f"glossary:{identity}", api_rate_limit)
    try:
        return glossaries.save(glossary_id, req.terms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/models")
async def models(request: Request) -> dict:
    identity = require_api_access(request, security_config)
    rate_limiter.check(f"models:{identity}", api_rate_limit)
    artifacts = scan_models(settings.models_dir)
    return {"count": len(artifacts), "models": [item.as_dict() for item in artifacts]}


@app.post("/hydra/v1/tasks/route")
async def route_task(task: HydraTask) -> dict:
    """Create and route a native HYDRA task without executing side effects."""
    try:
        trace_id, route = kernel.prepare(task)
        return {
            "task_id": str(task.id),
            "status": task.status.value,
            "trace_id": trace_id,
            "route": route.model_dump(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/hydra/v1/tasks/execute")
async def execute_task(task: HydraTask, request: Request) -> dict:
    """Execute a safe local cognitive task through the HYDRA kernel."""
    identity = require_api_access(request, security_config)
    rate_limiter.check(f"task-execute:{identity}", api_rate_limit)
    try:
        result = await kernel.run(task, llm)
        return result.model_dump(mode="json")
    except Exception as exc:
        from hydra.executor import UnsafePlan
        if isinstance(exc, UnsafePlan):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=502, detail="HYDRA execution failed") from exc




@app.get("/hydra/v1/admin/outbox/dead-letters")
async def list_dead_letters(request: Request) -> dict:
    identity = require_admin_access(request, security_config)
    rate_limiter.check(f"admin-dlq-list:{identity}", admin_rate_limit)
    security_audit.record(
        event_type="hydra.security.admin_access",
        endpoint="/hydra/v1/admin/outbox/dead-letters",
        outcome="allowed",
        identity_hash=identity,
    )
    messages = capture_uow.outbox.dead_letters()
    return {
        "count": len(messages),
        "messages": [
            {
                "id": str(message.id),
                "topic": message.topic,
                "aggregate_id": str(message.aggregate_id),
                "trace_id": message.trace_id,
                "attempts": message.attempts,
                "last_error": message.last_error,
                "dead_lettered_at": message.dead_lettered_at,
            }
            for message in messages
        ],
    }


@app.post("/hydra/v1/admin/outbox/dead-letters/{message_id}/retry")
async def retry_dead_letter(message_id: UUID, request: Request) -> dict:
    identity = require_admin_access(request, security_config)
    rate_limiter.check(f"admin-dlq-retry:{identity}", admin_rate_limit)
    requeued = capture_uow.outbox.requeue_dead_letter(message_id)
    security_audit.record(
        event_type="hydra.security.admin_access",
        endpoint="/hydra/v1/admin/outbox/dead-letters/retry",
        outcome="requeued" if requeued else "not_found",
        identity_hash=identity,
    )
    if not requeued:
        raise HTTPException(status_code=404, detail="Dead-letter message not found")
    return {"requeued": True, "message_id": str(message_id)}


@app.post("/hydra/v1/coding/verify-fix")
async def verify_code_fix(req: CodingRequest, request: Request) -> dict:
    """Generate and verify a patch in an expendable, container-tested workspace."""
    from uuid import uuid4

    identity = require_admin_access(request, security_config)
    rate_limiter.check(f"coding:{identity}", admin_rate_limit)
    security_audit.record(
        event_type="hydra.security.admin_access",
        endpoint="/hydra/v1/coding/verify-fix",
        outcome="allowed",
        identity_hash=identity,
    )

    task_id = uuid4()
    trace_id = uuid4().hex
    try:
        source = resolve_repository(settings.repositories_root, req.repository)
        agent = CodeAgent(
            llm,
            workspaces,
            artifacts,
            kernel.events,
            sandbox_factory=lambda root: OciSandbox(
                root,
                image=settings.sandbox_image,
                runtime=settings.sandbox_runtime,
            ),
        )
        result = await agent.run(
            task_id=task_id,
            trace_id=trace_id,
            goal=req.goal,
            source=source,
            max_tokens=budget.output_tokens(req.max_tokens),
        )
        belief_id = None
        corpus_status = None
        if result.accepted:
            belief, corpus_record = learning.capture_verified_patch(
                task_id=task_id,
                artifacts=result.artifacts,
            )
            belief_id = str(belief.belief_id)
            corpus_status = corpus_record.status.value

        verification = None
        if result.verification is not None:
            verification = {
                "baseline_failed": result.verification.baseline_failed,
                "targeted_target": result.verification.targeted_target,
                "targeted_passed": result.verification.targeted_passed,
                "full_suite_passed": result.verification.full_suite_passed,
                "syntax_passed": result.verification.syntax_passed,
                "improvement_demonstrated": (
                    result.verification.improvement_demonstrated
                ),
                "verified": result.verification.verified,
            }

        provenance.append(
            ProvenanceRecord(
                task_id=task_id,
                trace_id=trace_id,
                action="coding.patch_verification",
                inputs={"repository": req.repository},
                outputs={
                    "accepted": result.accepted,
                    "artifact_ids": [str(a.artifact_id) for a in result.artifacts],
                    "artifact_hashes": [a.sha256 for a in result.artifacts],
                    "verification": verification,
                },
            )
        )
        return {
            "task_id": str(task_id),
            "trace_id": trace_id,
            "accepted": result.accepted,
            "answer": result.answer,
            "artifact_ids": [str(a.artifact_id) for a in result.artifacts],
            "belief_id": belief_id,
            "corpus_status": corpus_status,
            "verification": verification,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="HYDRA coding verification failed") from exc
