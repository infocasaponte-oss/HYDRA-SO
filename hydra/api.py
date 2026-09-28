from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from hydra import __version__
from hydra.budgets import BudgetExceeded, RequestBudget
from hydra.config import settings
from hydra.model_scout import scan_models
from hydra.provider import LocalLLM
from hydra.translation import GlossaryStore, TranslationService

app = FastAPI(title="HYDRA-SO", version=__version__)
llm = LocalLLM(settings.llm_url)
budget = RequestBudget(
    settings.max_input_chars,
    settings.max_output_tokens,
    settings.max_translation_chunks,
)
glossaries = GlossaryStore()
translations = TranslationService(llm, budget, glossaries)


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
