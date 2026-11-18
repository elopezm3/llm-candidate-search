"""Module 7: run the workflow and the agent with Langfuse traces, score each trace, and scan traces for problems.

    python3 -m busqueda.trazar prompt          # creates/updates the versioned prompt "explicar-candidatos" (label production)
    python3 -m busqueda.trazar correr          # workflow on the 28 golden cases + agent on 6 (≈ USD 0.11, logged in COSTOS.md)
    python3 -m busqueda.trazar agente          # agent only, 28 golden cases, after leer_cv took a list of ids (≈ USD 0.20)
    python3 -m busqueda.trazar memoria         # same, with episodic memory (Module 8), compared with m8_base_agente.json
    python3 -m busqueda.trazar revisar         # silent-failure scan (lesson 21) + first problem per trace (lesson 17)

Every trace has user_id, session_id (one per posting), a tag with the system, and a `recall@5` score (lesson 14: scores on
the exact trace). Root observations are typed (chain for the workflow, agent for the agent).
"""
import atexit
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from langfuse import propagate_attributes

from data_extraction.extraer_cvs import MODEL, RAZONAMIENTO, anotar_costo
from data_extraction.rutas import PROYECTO, SALIDA_VACANTES

from .evaluar import recall_at_k
from .herramientas import ID_DE, costo
from .observabilidad import langfuse
from .workflow_lg import PROMPT_EXPLICAR, PROMPT_EXPLICAR_LOCAL

USUARIO = "reclutador-demo"
TOTAL = {"requests": 0, "entrada": 0, "salida": 0, "segundos": 0.0}
HERRAMIENTAS_ESPERADAS = {"buscar_semantica", "buscar_exacta", "leer_cv"}
MAX_TOOL_CALLS = 8  # = agent step budget. Was 6 (a guess): fired on 6/6 agent traces (normal runs use 7-8), pure noise
TRAZAS = PROYECTO / "data" / "processed" / "busqueda" / "m7_trazas.json"


def con_traza(sistema: str, caso: dict, correr) -> dict:
    """Runs `correr()` inside a root observation with user/session/tags, then scores recall@5 on that exact trace."""
    with langfuse.start_as_current_observation(name=sistema, as_type="agent" if sistema in ("agente", "memoria") else "chain",
                                               input={"consulta": caso["consulta"], "caso": caso["id"]}) as raiz:
        with propagate_attributes(user_id=USUARIO, session_id=f"vacante-{caso['id']}", tags=[sistema],
                                  metadata={"caso": caso["id"], "modelo": MODEL}):
            r = correr()
        raiz.update(output={"top5": [ID_DE.get(a, a) for a in r["top5"]], "cortado": r.get("cortado")})
        trace_id = langfuse.get_current_trace_id()
    if caso.get("esperados"):
        try:  # observability must never break the run: an overloaded Langfuse killed a 28-case run at case ~27 (Module 8)
            langfuse.create_score(trace_id=trace_id, name="recall@5", value=recall_at_k(r["top5"], caso["esperados"]), data_type="NUMERIC")
        except Exception as e:
            print(f"  WARNING: score not sent for {caso['id']} ({type(e).__name__}); the run continues", flush=True)
    return {**r, "trace_id": trace_id}


def revisar_trayectoria(llamadas: list[str]) -> list[str]:
    """Lesson 21's rules over the ordered tool calls of one agent trace ("nombre(args)")."""
    alertas = []
    for llamada, n in Counter(llamadas).items():
        if n >= 3:
            alertas.append(f"same call {n}x: {llamada[:60]}")
    raras = {l.split("(")[0] for l in llamadas} - HERRAMIENTAS_ESPERADAS
    if raras:
        alertas.append(f"unexpected tools: {sorted(raras)}")
    if len(llamadas) > MAX_TOOL_CALLS:
        alertas.append(f"{len(llamadas)} tool calls (> {MAX_TOOL_CALLS})")
    return alertas


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "correr"
    if accion == "prompt":
        p = langfuse.create_prompt(name=PROMPT_EXPLICAR, type="text", prompt=PROMPT_EXPLICAR_LOCAL, labels=["production"],
                                   config={"model": MODEL, "reasoning_effort": RAZONAMIENTO}, commit_message="Module 6 explanation prompt")
        print(f"prompt {p.name} v{p.version} labels {p.labels}")
    elif accion == "correr":
        from . import agente_lg, workflow_lg
        from .consultas import casos
        atexit.register(lambda: TOTAL["requests"] and anotar_costo("Module 7: traced runs (workflow 28 + agent 6)", "m7-v1",
                                                                   f"{MODEL} · {RAZONAMIENTO}", TOTAL["requests"], TOTAL["entrada"], TOTAL["salida"], costo(TOTAL)))
        vac = {json.loads(f.read_text())["source_file"]: json.loads(f.read_text())["vacante"] for f in SALIDA_VACANTES.glob("*.vac-v2.json")}
        trazas = []
        for c in casos():
            r = con_traza("workflow", c, lambda: workflow_lg.correr(c, vac.get(c.get("vacante_archivo"))))
            for k in TOTAL:
                TOTAL[k] += r["uso"].get(k, 0)
            trazas.append({"sistema": "workflow", "caso": c["id"], "trace_id": r["trace_id"]})
        for c in casos()[:6]:
            r = con_traza("agente", c, lambda: agente_lg.correr(c["consulta"]))
            for k in TOTAL:
                TOTAL[k] += r["uso"].get(k, 0)
            trazas.append({"sistema": "agente", "caso": c["id"], "trace_id": r["trace_id"], "cortado": r["cortado"]})
        langfuse.flush()
        TRAZAS.write_text(json.dumps(trazas, indent=2))
        print(f"{len(trazas)} traces · USD {costo(TOTAL):.4f} · e.g. {langfuse.get_trace_url(trace_id=trazas[-1]['trace_id'])}")
    elif accion in ("agente", "memoria"):  # memoria = same agent + the 2 most similar episodes (Module 8), own episode excluded
        import time
        from . import agente_lg
        from .consultas import casos
        etiqueta = "Module 8: agent × 28 with episodic memory" if accion == "memoria" else "Module 7: agent × 28 with batch leer_cv"
        atexit.register(lambda: TOTAL["requests"] and anotar_costo(etiqueta, "m8-v1" if accion == "memoria" else "m7-v2",
                                                                   f"{MODEL} · {RAZONAMIENTO}", TOTAL["requests"], TOTAL["entrada"], TOTAL["salida"], costo(TOTAL)))
        filas = []
        for c in casos():
            t0, antes = time.perf_counter(), costo(TOTAL)
            r = con_traza(accion, c, lambda: agente_lg.correr(c["consulta"], memoria=accion == "memoria", excluir=c["id"]))
            for k in TOTAL:
                TOTAL[k] += r["uso"].get(k, 0)
            lecturas = [h for h in r["herramientas"] if h.startswith("leer_cv")]
            filas.append({"caso": c["id"], "trace_id": r["trace_id"], "top5": [ID_DE.get(a, a) for a in r["top5"]], "recall": recall_at_k(r["top5"], c["esperados"]),
                          "pasos": r["uso"]["requests"], "tools": len(r["herramientas"]), "lecturas": len(lecturas),
                          "rendirse": bool(r["cortado"]), "seg": time.perf_counter() - t0, "costo": costo(TOTAL) - antes})
            print(f"  {c['id']}: recall {filas[-1]['recall']:.2f} · {filas[-1]['pasos']} steps · {len(lecturas)} leer_cv calls"
                  f"{' · GAVE UP' if r['cortado'] else ''}", flush=True)
        langfuse.flush()
        (TRAZAS.parent / ("m8_agente_memoria.json" if accion == "memoria" else "m7_agente_lote.json")).write_text(json.dumps(filas, indent=2))
        for nombre, sub in (("all 28", filas), ("first 6 (today: recall 0.611, gave up 2/6, p50 16.6 s, $0.0079)", filas[:6])):
            seg = sorted(f["seg"] for f in sub)
            print(f"{nombre}: recall@5 {sum(f['recall'] for f in sub)/len(sub):.3f} · steps {sum(f['pasos'] for f in sub)/len(sub):.1f} · "
                  f"gave up {sum(f['rendirse'] for f in sub)}/{len(sub)} · p50 {seg[len(seg)//2]:.1f} s · ${sum(f['costo'] for f in sub)/len(sub):.4f}/search")
        if accion == "memoria":
            from .herramientas import ARCHIVO_DE as ARCHIVO_DE_
            from .memoria import cargar
            base = json.loads((TRAZAS.parent / "m8_base_agente.json").read_text())
            con = {f["caso"]: f["top5"] for f in filas}
            print("\nRejected candidates on OTHER postings (did the lesson generalise?):")
            for ep_caso, ep in cargar().items():
                for cid in ep["quitados"]:
                    antes = [k for k, v in base.items() if cid in v["top5"] and k != ep_caso]
                    despues = [k for k in con if cid in con[k] and k != ep_caso]
                    correctos = [c["id"] for c in casos() if ARCHIVO_DE_[cid] in c["esperados"]]
                    print(f"  {cid} (rejected on {ep_caso}): wrongly recommended before in {len([k for k in antes if k not in correctos])} "
                          f"→ with memory {len([k for k in despues if k not in correctos])} · where it IS correct {correctos}: "
                          f"kept before {[k for k in correctos if k in antes]} → with memory {[k for k in correctos if k in despues]}")
    elif accion == "revisar":
        trazas = json.loads(TRAZAS.read_text())
        print("Silent-failure scan (agent traces) and first problem per trace:")
        for t in trazas:
            obs = langfuse.api.observations.get_many(trace_id=t["trace_id"], fields="core,basic,io", limit=100).data
            obs = sorted(obs, key=lambda o: o.start_time)
            tools = [f"{o.name}({str(o.input)[:60]})" for o in obs if str(getattr(o, "type", "")).upper().endswith("TOOL")]
            alertas = revisar_trayectoria(tools) if t["sistema"] == "agente" else []
            problema = next((o for o in obs if str(getattr(o, "level", "")).upper().endswith(("WARNING", "ERROR"))), None)
            if alertas or problema:
                print(f"  {t['sistema']:8} {t['caso']}: {'; '.join(alertas) or '-'}"
                      f"{' | first problem: ' + problema.name + ' → ' + str(problema.status_message)[:80] if problema else ''}")
                print(f"           {langfuse.get_trace_url(trace_id=t['trace_id'])}")
