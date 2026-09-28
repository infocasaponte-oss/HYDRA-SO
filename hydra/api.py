from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from hydra import __version__
from hydra.artifacts import ArtifactStore
from hydra.budgets import BudgetExceeded, RequestBudget
from hydra.code_agent import CodeAgent
from hydra.coding_request import CodingRequest, resolve_repository
from hydra.config import settings
from hydra.contracts import HydraTask
from hydra.kernel import HydraKernel
from hydra.model_scout import scan_models
from hydra.provenance import ProvenanceLedger, ProvenanceRecord
from hydra.provider import LocalLLM
from hydra.translation import GlossaryStore, TranslationService
from hydra.workspaces import WorkspaceManager

app = FastAPI(title="HYDRA-SO", version=__version__)
llm = LocalLLM(settings.llm_url)
budget = RequestBudget(
    settings.max_input_chars,
    settings.max_output_tokens,
    settings.max_translation_chunks,
)
glossaries = GlossaryStore()
translations = TranslationService(llm, budget, glossaries)
kernel = HydraKernel()
artifacts = ArtifactStore()
provenance = ProvenanceLedger()
workspaces = WorkspaceManager()


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
    return {"hydra": "ok", "version": __version__, "llm": await llm.health()}


@app.post("/v1/chat")
async def chat(req: ChatRequest) -> dict:
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
async def translate(req: TranslationRequest) -> dict:
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
async def put_glossary(glossary_id: str, req: GlossaryRequest) -> dict:
    try:
        return glossaries.save(glossary_id, req.terms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/models")
async def models() -> dict:
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
async def execute_task(task: HydraTask) -> dict:
    """Execute a safe local cognitive task through the HYDRA kernel."""
    try:
        result = await kernel.run(task, llm)
        return result.model_dump(mode="json")
    except Exception as exc:
        from hydra.executor import UnsafePlan
        if isinstance(exc, UnsafePlan):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=502, detail="HYDRA execution failed") from exc


@app.post("/hydra/v1/coding/verify-fix")
async def verify_code_fix(req: CodingRequest) -> dict:
    """Generate and verify a patch in an expendable, container-tested workspace."""
    from uuid import uuid4

    task_id = uuid4()
    trace_id = uuid4().hex
    try:
        source = resolve_repository(settings.repositories_root, req.repository)
        agent = CodeAgent(llm, workspaces, artifacts, kernel.events)
        result = await agent.run(
            task_id=task_id,
            trace_id=trace_id,
            goal=req.goal,
            source=source,
            max_tokens=budget.output_tokens(req.max_tokens),
        )
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
                },
            )
        )
        return {
            "task_id": str(task_id),
            "trace_id": trace_id,
            "accepted": result.accepted,
            "answer": result.answer,
            "artifact_ids": [str(a.artifact_id) for a in result.artifacts],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="HYDRA coding verification failed") from exc
