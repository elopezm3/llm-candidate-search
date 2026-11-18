"""Module 6: the LangGraph versions on the golden dataset, next to the Module 5 plain-Python numbers for the same cases.

    python3 -m busqueda.comparar_m6        # workflow on all 28 + agent on the first 5 (≈ USD 0.10, logged in COSTOS.md)
"""
import atexit
import json
from statistics import mean

from data_extraction.extraer_cvs import MODEL, RAZONAMIENTO, anotar_costo
from data_extraction.rutas import PROYECTO, SALIDA_VACANTES

from . import agente_lg, workflow_lg
from .consultas import casos
from .evaluar import recall_at_k
from .herramientas import costo

TOTAL = {"requests": 0, "entrada": 0, "salida": 0, "segundos": 0.0}
N_AGENTE = 5
M5 = {f["id"]: f for f in json.loads((PROYECTO / "data/processed/busqueda/m5/comparacion_todos.json").read_text())}


def _sumar(uso):
    for k in TOTAL:
        TOTAL[k] += uso.get(k, 0)


if __name__ == "__main__":
    atexit.register(lambda: TOTAL["requests"] and anotar_costo("Module 6: LangGraph workflow (28) + agent (5)", "m6-v1",
                                                               f"{MODEL} · {RAZONAMIENTO}", TOTAL["requests"], TOTAL["entrada"], TOTAL["salida"], costo(TOTAL)))
    vac = {json.loads(f.read_text())["source_file"]: json.loads(f.read_text())["vacante"] for f in SALIDA_VACANTES.glob("*.vac-v2.json")}
    cs = casos()
    w = []
    for c in cs:
        r = workflow_lg.correr(c, vac.get(c.get("vacante_archivo")))
        _sumar(r["uso"])
        w.append({"id": c["id"], "recall@5": recall_at_k(r["top5"], c["esperados"]), "usd": costo(r["uso"]), "llamadas": r["uso"]["requests"]})
    print(f"workflow LangGraph (28): recall@5 {mean(x['recall@5'] for x in w):.2f} · calls/query {mean(x['llamadas'] for x in w):.1f} · "
          f"USD/query {mean(x['usd'] for x in w):.4f}   | Module 5 plain Python: recall@5 {mean(M5[x['id']]['workflow']['recall@5'] for x in w):.2f}")
    a = []
    for c in cs[:N_AGENTE]:
        r = agente_lg.correr(c["consulta"])
        _sumar(r["uso"])
        a.append({"id": c["id"], "recall@5": recall_at_k(r["top5"], c["esperados"]), "llamadas": r["uso"]["requests"], "usd": costo(r["uso"]),
                  "cortado": r["cortado"], "m5": M5[c["id"]]["agente"]})
        print(f"  agent {c['id']}: LangGraph r@5 {a[-1]['recall@5']:.2f} · {a[-1]['llamadas']} calls · ${a[-1]['usd']:.4f}"
              f"{' · gave up (' + r['cortado'] + ')' if r['cortado'] else ''}   | Module 5: r@5 {a[-1]['m5']['recall@5']:.2f} · {a[-1]['m5']['llamadas']} calls")
    print(f"agent LangGraph ({N_AGENTE}): recall@5 {mean(x['recall@5'] for x in a):.2f} · calls/query {mean(x['llamadas'] for x in a):.1f} · "
          f"USD/query {mean(x['usd'] for x in a):.4f}   | Module 5 same cases: recall@5 {mean(x['m5']['recall@5'] for x in a):.2f} · "
          f"calls/query {mean(x['m5']['llamadas'] for x in a):.1f}")
