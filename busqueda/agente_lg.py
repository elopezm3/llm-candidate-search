"""Module 6, script 2: the Module 5 agent as a LangGraph graph.

    START → llm ─ tool calls ──→ herramientas ─ steps/time/tokens left ──→ llm
                │                              └ near the limit ─────────→ rendirse → END
                └ no tool calls → finalizar → END

- `recursion_limit` caps graph steps (each turn = llm + herramientas = 2 steps); `RemainingSteps` lets the graph give up
  gracefully one full turn before the cap (lesson 19: leave a turn plus the exit path).
- Tool failures come back as text the model can act on (`ejecutar`, as in Module 5), so one Qdrant hiccup doesn't kill the run.
- Messages are plain dicts in state, appended with a reducer; Gemini's thought signatures stay inside the tool calls.
"""
import operator
import re
import time
from typing import Annotated, TypedDict

from langfuse import observe
from langgraph.graph import END, START, StateGraph
from langgraph.managed import RemainingSteps

from .agente import MAX_PASOS, MAX_SEGUNDOS, MAX_TOKENS, SISTEMA
from .herramientas import ARCHIVO_DE, HERRAMIENTAS, ejecutar, llamar_llm
from .memoria import como_ejemplos, similares
from .observabilidad import langfuse
from .workflow_lg import sumar_uso

RECURSION_LIMIT = 2 * MAX_PASOS + 2  # 8 llm turns + the exit node


def unir_sin_repetir(a: list, b: list) -> list:
    return a + [x for x in b if x not in a]


class EstadoAgente(TypedDict, total=False):
    messages: Annotated[list[dict], operator.add]
    remaining_steps: RemainingSteps
    uso: Annotated[dict, sumar_uso]
    vistos: Annotated[list[str], unir_sin_repetir]
    inicio: float
    top5: list[str]
    cortado: str | None
    herramientas_usadas: Annotated[list[str], operator.add]


@observe(name="llm")
def llm(estado: EstadoAgente) -> EstadoAgente:
    uso = {"requests": 0, "entrada": 0, "salida": 0, "segundos": 0.0}
    msg = llamar_llm(estado["messages"], uso, HERRAMIENTAS).choices[0].message
    nuevo = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        nuevo["tool_calls"] = [tc.model_dump(exclude_none=True) for tc in msg.tool_calls]
    return {"messages": [nuevo], "uso": uso}


@observe(name="herramientas")
def herramientas(estado: EstadoAgente) -> EstadoAgente:
    msgs, usadas, vistos = [], [], []
    for tc in estado["messages"][-1]["tool_calls"]:
        resultado = ejecutar(tc["function"]["name"], tc["function"]["arguments"])
        usadas.append(f"{tc['function']['name']}({tc['function']['arguments'][:60]})")
        vistos += re.findall(r"cv-\d{2}", resultado)
        msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": resultado})
    return {"messages": msgs, "herramientas_usadas": usadas, "vistos": vistos}


@observe(name="finalizar")
def finalizar(estado: EstadoAgente) -> EstadoAgente:
    ids = list(dict.fromkeys(re.findall(r"cv-\d{2}", estado["messages"][-1]["content"])))
    return {"top5": [ARCHIVO_DE[i] for i in ids if i in ARCHIVO_DE][:5], "cortado": None}


@observe(name="rendirse")
def rendirse(estado: EstadoAgente) -> EstadoAgente:
    """Best available instead of an exception: candidates in the order the searches surfaced them."""
    motivo = ("pasos" if estado["remaining_steps"] <= 3 else "tiempo" if time.time() - estado["inicio"] > MAX_SEGUNDOS else "tokens")
    langfuse.update_current_span(level="WARNING", status_message=f"agent stopped by the {motivo} limit, returning best available")
    return {"top5": [ARCHIVO_DE[i] for i in estado.get("vistos", []) if i in ARCHIVO_DE][:5], "cortado": motivo}


def despues_de_llm(estado: EstadoAgente) -> str:
    return "herramientas" if estado["messages"][-1].get("tool_calls") else "finalizar"


def despues_de_herramientas(estado: EstadoAgente) -> str:
    if (estado["remaining_steps"] <= 3 or time.time() - estado["inicio"] > MAX_SEGUNDOS
            or estado.get("uso", {}).get("entrada", 0) > MAX_TOKENS):
        return "rendirse"
    return "llm"


def construir():
    g = StateGraph(EstadoAgente)
    for nombre, f in (("llm", llm), ("herramientas", herramientas), ("finalizar", finalizar), ("rendirse", rendirse)):
        g.add_node(nombre, f)
    g.add_edge(START, "llm")
    g.add_conditional_edges("llm", despues_de_llm, ["herramientas", "finalizar"])
    g.add_conditional_edges("herramientas", despues_de_herramientas, ["llm", "rendirse"])
    g.add_edge("finalizar", END)
    g.add_edge("rendirse", END)
    return g.compile()


APP = construir()


def correr(consulta: str, memoria: bool = False, excluir: str | None = None) -> dict:
    """memoria=True adds the 2 most similar episodes (Module 8) to the user message; `excluir` = the case's own episode."""
    ejemplos = como_ejemplos(similares(consulta, excluir=excluir)) if memoria else ""
    pedido = f"Búsqueda: {consulta}" + (f"\n\n{ejemplos}" if ejemplos else "")
    r = APP.invoke({"messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": pedido}],
                    "inicio": time.time()}, {"recursion_limit": RECURSION_LIMIT})
    return {"top5": r.get("top5", []), "uso": r["uso"], "cortado": r.get("cortado"), "herramientas": r.get("herramientas_usadas", [])}
