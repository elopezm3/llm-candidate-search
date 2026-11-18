"""Module 5: workflow vs agent on the golden dataset (recall@5, reciprocal rank in the top 5, model calls, tokens, cost, time).

    python3 -m busqueda.comparar_m5 3          # pilot: first 3 golden cases (both systems)
    python3 -m busqueda.comparar_m5 todos      # all 28 cases
Gemini costs are logged in COSTOS.md. MAX_REQUESTS caps the whole run.
"""
import atexit
import json
import sys
from statistics import mean

from data_extraction.extraer_cvs import MODEL, RAZONAMIENTO, anotar_costo
from data_extraction.rutas import PROYECTO, SALIDA_VACANTES

from .agente import agente
from .consultas import casos
from .evaluar import recall_at_k, reciprocal_rank
from .herramientas import costo
from .workflow import workflow

MAX_REQUESTS = 300
SALIDA = PROYECTO / "data" / "processed" / "busqueda" / "m5"
TOTAL = {"requests": 0, "entrada": 0, "salida": 0, "segundos": 0.0}


def _sumar(uso):
    for k in TOTAL:
        TOTAL[k] += uso[k]


if __name__ == "__main__":
    atexit.register(lambda: TOTAL["requests"] and anotar_costo(
        f"Module 5: workflow vs agent ({sys.argv[1] if len(sys.argv) > 1 else '3'} cases)", "m5-v1", f"{MODEL} · {RAZONAMIENTO}",
        TOTAL["requests"], TOTAL["entrada"], TOTAL["salida"], costo(TOTAL)))
    n = sys.argv[1] if len(sys.argv) > 1 else "3"
    cs = casos() if n == "todos" else casos()[:int(n)]
    vac = {json.loads(f.read_text())["source_file"]: json.loads(f.read_text())["vacante"] for f in SALIDA_VACANTES.glob("*.vac-v2.json")}
    SALIDA.mkdir(parents=True, exist_ok=True)
    filas = []
    for c in cs:
        if TOTAL["requests"] >= MAX_REQUESTS:
            print("request cap reached, stopping"); break
        v = vac[c["vacante_archivo"]] if c["tipo"] == "vacante" else None
        w = workflow(c, v); _sumar(w["uso"])
        a = agente(c["consulta"]); _sumar(a["uso"])
        fila = {"id": c["id"], "esperados": c["esperados"],
                "workflow": {"recall@5": recall_at_k(w["top5"], c["esperados"]), "rr": reciprocal_rank(w["top5"], c["esperados"]),
                             "llamadas": w["uso"]["requests"], "tokens": w["uso"]["entrada"] + w["uso"]["salida"], "usd": costo(w["uso"]),
                             "segundos": w["uso"]["segundos"], "top5": w["top5"]},
                "agente": {"recall@5": recall_at_k(a["top5"], c["esperados"]), "rr": reciprocal_rank(a["top5"], c["esperados"]),
                           "llamadas": a["uso"]["requests"], "tokens": a["uso"]["entrada"] + a["uso"]["salida"], "usd": costo(a["uso"]),
                           "segundos": a["uso"]["segundos"], "cortado": a["cortado"], "herramientas": a["herramientas"], "top5": a["top5"]}}
        filas.append(fila)
        print(f"{c['id']}  workflow r@5 {fila['workflow']['recall@5']:.2f} · 1 call · ${fila['workflow']['usd']:.4f}   |   "
              f"agent r@5 {fila['agente']['recall@5']:.2f} · {a['uso']['requests']} calls · {fila['agente']['tokens']:,} tok · ${fila['agente']['usd']:.4f}"
              f"{' · CUT ' + a['cortado'] if a['cortado'] else ''} · tools: {len(a['herramientas'])}", flush=True)
    (SALIDA / f"comparacion_{n}.json").write_text(json.dumps(filas, ensure_ascii=False, indent=2))
    for s in ("workflow", "agente"):
        print(f"\n{s:8} recall@5 {mean(f[s]['recall@5'] for f in filas):.2f} · RR@5 {mean(f[s]['rr'] for f in filas):.2f} · "
              f"calls/query {mean(f[s]['llamadas'] for f in filas):.1f} · tokens/query {mean(f[s]['tokens'] for f in filas):,.0f} · "
              f"USD/query {mean(f[s]['usd'] for f in filas):.4f} · s/query {mean(f[s]['segundos'] for f in filas):.1f}")
