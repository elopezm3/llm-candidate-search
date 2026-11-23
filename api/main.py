"""Local HTTP API over the Module 5 workflow, for the Next.js UI in web/.

    uvicorn api.main:app --port 8000        # from project/

LOCAL ONLY: it uses your Gemini + Voyage keys and the real CVs. The public demo is static (pre-computed JSON), no API.
- A posting → its extracted requirements → dense search with filters. Free text → input guardrail first (blocked = $0).
- 1 Gemini call per search. `LIMITE_BUSQUEDAS` caps each server run; the run's cost goes to COSTOS.md on shutdown.
"""
import atexit
import json
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from busqueda.consultas import consulta_de_vacante
from busqueda.guardrails import entrada, salida
from busqueda.herramientas import costo, leer_cv
from busqueda.workflow import workflow
from data_extraction.extraer_cvs import MODEL, RAZONAMIENTO, anotar_costo
from data_extraction.rutas import SALIDA_VACANTES

LIMITE_BUSQUEDAS = int(os.getenv("LIMITE_BUSQUEDAS", "20"))
TOTAL = {"requests": 0, "entrada": 0, "salida": 0, "segundos": 0.0, "busquedas": 0}
VACANTES = {d["source_file"]: d["vacante"] for d in (json.loads(f.read_text()) for f in sorted(SALIDA_VACANTES.glob("*.vac-v2.json")))}

atexit.register(lambda: TOTAL["requests"] and anotar_costo(
    f"Web API: {TOTAL['busquedas']} searches", "web-v1", f"{MODEL} · {RAZONAMIENTO}",
    TOTAL["requests"], TOTAL["entrada"], TOTAL["salida"], costo(TOTAL)))

app = FastAPI(title="llm-candidate-search (local)")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3001"], allow_methods=["*"], allow_headers=["*"])


class Busqueda(BaseModel):
    consulta: str | None = Field(None, max_length=500)
    vacante: str | None = None  # source_file of an extracted posting


@app.get("/vacantes")
def vacantes() -> list[dict]:
    return [{"archivo": a, "cargo": v["cargo"]} for a, v in VACANTES.items()]


def por_candidato(explicacion: str, ids: list[str]) -> dict[str, str]:
    """The prompt asks for lines starting with the id; anything unmatched stays in the raw text."""
    out = {}
    for linea in explicacion.splitlines():
        m = re.search(r"cv-\d+", linea, re.IGNORECASE)
        if m and m.group(0).lower() in ids:
            out.setdefault(m.group(0).lower(), re.sub(r"^\W*cv-\d+\W*", "", linea, flags=re.IGNORECASE).strip())
    return out


@app.post("/buscar")
def buscar(b: Busqueda) -> dict:
    if b.vacante:
        if b.vacante not in VACANTES:
            raise HTTPException(404, "unknown posting")
        v, consulta = VACANTES[b.vacante], consulta_de_vacante(VACANTES[b.vacante])
    elif b.consulta and b.consulta.strip():
        v, consulta = None, b.consulta.strip()
        etiqueta, respuesta = entrada(consulta)
        if respuesta:
            return {"bloqueado": etiqueta, "respuesta": respuesta, "candidatos": []}
    else:
        raise HTTPException(422, "send 'consulta' or 'vacante'")
    if TOTAL["busquedas"] >= LIMITE_BUSQUEDAS:
        raise HTTPException(429, f"search cap for this run reached ({LIMITE_BUSQUEDAS}); restart the API to reset it")
    TOTAL["busquedas"] += 1
    w = workflow({"consulta": consulta}, v)
    for k in ("requests", "entrada", "salida", "segundos"):
        TOTAL[k] += w["uso"][k]
    explicacion = salida(w["explicacion"])
    motivos = por_candidato(explicacion, w["ids"])
    candidatos = [{**leer_cv(a), "motivo": motivos.get(i)} for a, i in zip(w["top5"], w["ids"])]
    return {"consulta": consulta, "candidatos": candidatos, "explicacion": explicacion,
            "usd": round(costo(w["uso"]), 5), "usd_sesion": round(costo(TOTAL), 5)}
