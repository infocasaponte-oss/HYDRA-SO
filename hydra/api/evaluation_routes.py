# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Small human review UI for the pinned external holdout; no automatic certification."""
import asyncio
import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Literal

from hydra.training.verified_corpus import sha256

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/external-evaluation-v1"
ANSWERS = ROOT / "docs/evidence/external-evaluation-v5.json"
REVIEWS = ROOT / "runtime/external-evaluation-v5-reviews.json"
LOCK = asyncio.Lock()


class Review(BaseModel):
    case_id: int = Field(ge=1,le=100)
    decision: Literal["correct", "incorrect", "ambiguous"]
    reviewer: str = Field(min_length=1,max_length=120)
    note: str = Field(default="",max_length=2000)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def cases():
    manifest=json.loads((DATA/"manifest.json").read_text(encoding="utf-8"))
    if sha256(DATA/"cases.json") != manifest["cases_sha256"]:
        raise HTTPException(409,"El test congelado ha cambiado")
    return json.loads((DATA/"cases.json").read_text(encoding="utf-8-sig")),manifest


def register(app,secured):
    @app.get("/hydra/v1/evaluation/review",response_class=HTMLResponse)
    async def page():
        return HTMLResponse((Path(__file__).with_name("evaluation_review.html")).read_text(encoding="utf-8"))

    @app.get("/hydra/v1/evaluation/cases",dependencies=secured)
    async def get_cases():
        rows,manifest=cases()
        report=json.loads(ANSWERS.read_text(encoding="utf-8")) if ANSWERS.exists() else {}
        saved=json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.exists() else {}
        if report and report.get("dataset_sha256") != manifest["cases_sha256"]:
            raise HTTPException(409,"Las respuestas pertenecen a otro test")
        if saved and saved.get("artifact_sha256") != report.get("artifact_sha256"):
            saved={}
        return dict(cases=rows,answers=report,reviews=saved,manifest=manifest)

    @app.post("/hydra/v1/evaluation/review",dependencies=secured)
    async def save_review(body:Review):
        rows,manifest=cases()
        if body.case_id not in {r["id"] for r in rows} or not ANSWERS.exists():
            raise HTTPException(409,"Todavía falta la inferencia real de este test")
        report=json.loads(ANSWERS.read_text(encoding="utf-8"))
        if body.artifact_sha256 != report.get("artifact_sha256") or report.get("dataset_sha256") != manifest["cases_sha256"]:
            raise HTTPException(409,"Modelo o test distintos de los revisados")
        answer=next((a for a in report.get("cases",[]) if a["id"]==body.case_id),None)
        if not answer or "output" not in answer or answer.get("error"):
            raise HTTPException(409,"Este caso no tiene una respuesta real revisable")
        if body.decision=="ambiguous" and not body.note.strip():
            raise HTTPException(422,"Indica qué interpretación o referencia es ambigua")
        if not body.reviewer.strip():
            raise HTTPException(422,"Indica el nombre del revisor")
        async with LOCK:
            saved=json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.exists() else {}
            if saved and saved.get("artifact_sha256") != body.artifact_sha256:
                raise HTTPException(409,"Existen revisiones de otro modelo; no se sobrescriben")
            saved.update(artifact_sha256=body.artifact_sha256,dataset_sha256=manifest["cases_sha256"],approved=False)
            saved.setdefault("cases",{})[str(body.case_id)] = body.model_dump()
            saved["reviewed"]=len(saved["cases"])
            saved["correct"]=sum(c["decision"]=="correct" for c in saved["cases"].values())
            saved["ambiguous"]=sum(c["decision"]=="ambiguous" for c in saved["cases"].values())
            # Every case remains in the denominator: ambiguity cannot silently improve accuracy.
            saved["accuracy_all_cases"]=saved["correct"]/len(rows)
            saved["complete"]=saved["reviewed"]==len(rows)
            REVIEWS.parent.mkdir(parents=True,exist_ok=True)
            tmp=REVIEWS.with_suffix(".tmp")
            tmp.write_text(json.dumps(saved,indent=2,ensure_ascii=False),encoding="utf-8")
            tmp.replace(REVIEWS)
            return saved
