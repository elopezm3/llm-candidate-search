"""Module 5: the shared search functions. The workflow calls them as fixed steps; the agent gets them as tools.

Search results carry only an id and a short summary (lesson 20: the model should pay only for what it chooses to read);
`leer_cv` returns the Module 1 structured summary. Short ids ("cv-07") so the model can't mistype long file names,
and errors are written for the model ("ids look like cv-07"), not as stack traces (lesson 19).
"""
import atexit
import json
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

from data_extraction.extraer_cvs import MODEL, PRECIO_USD_POR_MILLON, RAZONAMIENTO
from data_extraction.rutas import SALIDA_CVS

from .evaluar import embeber
from .guardrails import datos_seguros
from .observabilidad import langfuse
from .hibrida import COLECCION, buscar as _buscar
from .indexar import DIM, MODELO, cliente

load_dotenv()
gemini = OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url="https://generativelanguage.googleapis.com/v1beta/openai/", max_retries=0)

_CVS = {json.loads(f.read_text())["source_file"]: json.loads(f.read_text())
        for f in sorted(SALIDA_CVS.glob("*.cv-v8.json")) if not f.name.startswith("_")}
IDS = SALIDA_CVS.parent / "ids.json"  # data/processed/ids.json


def ids_estables(archivos, ruta=IDS) -> dict[str, str]:
    """Fixed ids. They used to be alphabetical positions, so deleting one candidate (Module 8) would shift everyone after
    them and old drafts/traces/episodes would point at the wrong person. New files get the next number; a deleted
    candidate's entry becomes "_borrado_cv-NN", so its number is never reused. First run reproduces the old positions."""
    ids = json.loads(ruta.read_text()) if ruta.exists() else {}
    n, antes = max([int(v[3:]) for v in ids.values()] + [0]), len(ids)
    for a in sorted(archivos):
        if a not in ids:
            n += 1
            ids[a] = f"cv-{n:02d}"
    if len(ids) != antes:
        ruta.write_text(json.dumps(ids, ensure_ascii=False, indent=1))
    return {a: ids[a] for a in archivos}


ID_DE = ids_estables(_CVS)
ARCHIVO_DE = {v: k for k, v in ID_DE.items()}
MAX_LECTURAS = 6  # per leer_cv call, = the reading budget in the agent prompt
_q, _avg_len = None, None
atexit.register(lambda: _q is not None and _q.close())


def _cliente():
    global _q, _avg_len
    if _q is None:
        from statistics import mean
        _q = cliente()
        _avg_len = mean(len(p.payload["texto"].split()) for p in _q.scroll(COLECCION, limit=10_000, with_payload=["texto"])[0])
    return _q, _avg_len


def resumen_corto(archivo: str) -> str:
    cv = _CVS[archivo]["cv"]
    cargo = cv["experiencia"][0]["cargo"] if cv["experiencia"] else "sin experiencia listada"
    anos = _CVS[archivo]["anos_experiencia"]
    return f"{cargo[:45]} · {anos if anos is not None else '?'} años"


def buscar(consulta: str, sistema: str = "dense", filtro=None, k: int = 8) -> list[str]:
    """Ranked CV file names (best chunk per CV). One retriever span per search (lesson 8): you can see which search
    brought each candidate. An empty result is marked WARNING (lesson 17: left the happy path)."""
    with langfuse.start_as_current_observation(name=f"buscar_{sistema}", as_type="retriever",
                                               input={"consulta": consulta, "sistema": sistema, "k": k, "con_filtro": filtro is not None}) as span:
        q, avg_len = _cliente()
        v = embeber("voyage", MODELO, DIM, {consulta: consulta}, "query")[consulta]
        ids = _buscar(q, sistema, v, consulta if sistema != "dense" else "", avg_len, filtro=filtro, limite=k)
        span.update(output=[{"id": ID_DE[a], "archivo": a} for a in ids],
                    **({"level": "WARNING", "status_message": "search returned no CVs"} if not ids else {}))
        return ids


def leer_cv(archivo: str) -> dict:
    r = _CVS[archivo]
    cv = r["cv"]
    return {
        "id": ID_DE[archivo], "nombre": cv["nombre_completo"], "anos_experiencia": r["anos_experiencia"],
        "experiencia": [f"{e['cargo']} @ {e['empresa']} ({e['fecha_inicio'] or '?'}–{e['fecha_fin'] or ('hoy' if e['actual'] else '?')})"
                        for e in cv["experiencia"][:6]],
        "educacion": [f"{e['titulo']} ({e['nivel']})" for e in cv["educacion"] if e["nivel"] != "curso"][:4],
        "tecnologias": cv["tecnologias"][:15],
        "idiomas": [f"{i['idioma']} {i['nivel'] or ''}".strip() for i in cv["idiomas"]],
    }


# ---- tool layer for the agent (JSON in, JSON out, errors as text) ----
HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "buscar_semantica",
        "description": "Busca hojas de vida por SIGNIFICADO (perfil, cargo, tipo de experiencia). Úsala para describir el rol. "
                       "Devuelve hasta 8 candidatos con id y un resumen de una línea.",
        "parameters": {"type": "object", "properties": {"consulta": {"type": "string", "description": "Descripción corta del perfil buscado, en español"}},
                       "required": ["consulta"]}}},
    {"type": "function", "function": {
        "name": "buscar_exacta",
        "description": "Busca hojas de vida que mencionen PALABRAS EXACTAS: herramientas, certificaciones, empresas (BM25). "
                       "Úsala solo con términos específicos, no con frases generales. Devuelve hasta 8 candidatos con id y resumen.",
        "parameters": {"type": "object", "properties": {"consulta": {"type": "string", "description": "Términos exactos, ej. 'Airflow Spark'"}},
                       "required": ["consulta"]}}},
    {"type": "function", "function": {
        "name": "leer_cv",
        "description": "Devuelve el resumen estructurado de una o VARIAS hojas de vida (hasta 6 por llamada): cargos con empresa y "
                       "fechas, años de experiencia, estudios, tecnologías e idiomas. Pide en UNA sola llamada todas las que quieras "
                       "verificar antes de recomendar.",
        "parameters": {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"},
                                                                "description": "Ids de los candidatos, ej. [\"cv-07\", \"cv-12\"]"}},
                       "required": ["ids"]}}},
]


def ejecutar(nombre: str, argumentos: str) -> str:
    """Runs a tool for the agent (one `tool` span each); a failure comes back as text the model can act on, marked WARNING."""
    with langfuse.start_as_current_observation(name=nombre, as_type="tool", input=argumentos) as span:
        avisos = []
        resultado = datos_seguros(_ejecutar(nombre, argumentos), avisos)  # Module 8: CV data is escaped and checked
        nivel = ({"level": "WARNING", "status_message": f"suspicious text in CV data: {avisos}"[:200]} if avisos else
                 {"level": "WARNING", "status_message": resultado[:200]} if resultado.startswith(("Error", "Sin resultados")) else {})
        span.update(output=resultado, **nivel)
        return resultado


def _ejecutar(nombre: str, argumentos: str) -> str:
    try:
        args = json.loads(argumentos or "{}")
        if nombre in ("buscar_semantica", "buscar_exacta"):
            if not args.get("consulta", "").strip():
                return "Error: 'consulta' está vacía. Escribe qué perfil o qué términos buscar."
            ids = buscar(args["consulta"], "dense" if nombre == "buscar_semantica" else "bm25")
            if not ids:
                return "Sin resultados: ninguna hoja de vida contiene esos términos. Prueba con buscar_semantica o con otros términos."
            return json.dumps([{"id": ID_DE[a], "resumen": resumen_corto(a)} for a in ids], ensure_ascii=False)
        if nombre == "leer_cv":  # batch: one step reads several CVs (Module 7, trace V03: one read per step ate the budget)
            ids = args.get("ids") or args.get("id") or []
            ids = [ids] if isinstance(ids, str) else ids
            if not ids:
                return "Error: 'ids' está vacío. Pasa una lista de ids con la forma cv-07, que salen de los resultados de búsqueda."
            fichas = [leer_cv(ARCHIVO_DE[i]) for i in (str(x).strip().lower() for x in ids[:MAX_LECTURAS]) if i in ARCHIVO_DE]
            malos = [x for x in ids[:MAX_LECTURAS] if str(x).strip().lower() not in ARCHIVO_DE]
            if not fichas:
                return f"Error: no existen los ids {malos!r}. Los ids tienen la forma cv-07 y salen de los resultados de búsqueda."
            avisos = ([f"ids inexistentes: {malos}"] if malos else []) + \
                     ([f"solo se leyeron las primeras {MAX_LECTURAS} de {len(ids)}"] if len(ids) > MAX_LECTURAS else [])
            return json.dumps({"cvs": fichas, **({"avisos": avisos} if avisos else {})}, ensure_ascii=False)
        return f"Error: la herramienta {nombre!r} no existe. Usa buscar_semantica, buscar_exacta o leer_cv."
    except Exception as e:  # never crash the loop: the model reads the error and decides (lesson 19)
        return f"Error al ejecutar {nombre}: {type(e).__name__}: {e}"


def llamar_llm(mensajes: list[dict], uso: dict, herramientas: list | None = None, prompt=None, nombre: str = "gemini"):
    """One Gemini call as a Langfuse `generation` (model, tokens, cost) linked to its versioned prompt if given.
    Langfuse's price table doesn't know gemini-3.8-flash, so the cost is ingested from our own prices (lesson 13)."""
    with langfuse.start_as_current_observation(name=nombre, as_type="generation", model=MODEL, input=mensajes, prompt=prompt,
                                               model_parameters={"reasoning_effort": RAZONAMIENTO, "tools": len(herramientas or [])}) as gen:
        r = _llamar_llm(mensajes, uso, herramientas)
        msg = r.choices[0].message
        salida = r.usage.total_tokens - r.usage.prompt_tokens
        gen.update(output={"content": msg.content, "tool_calls": [tc.function.model_dump() for tc in msg.tool_calls or []]},
                   usage_details={"input": r.usage.prompt_tokens, "output": salida},
                   cost_details={"input": r.usage.prompt_tokens * PRECIO_USD_POR_MILLON["entrada"] / 1e6,
                                 "output": salida * PRECIO_USD_POR_MILLON["salida"] / 1e6})
        return r


def _llamar_llm(mensajes: list[dict], uso: dict, herramientas: list | None = None):
    t0 = time.perf_counter()
    for espera in (30, 60, None):
        try:
            r = gemini.chat.completions.create(model=MODEL, reasoning_effort=RAZONAMIENTO, messages=mensajes,
                                               **({"tools": herramientas} if herramientas else {}))
            break
        except Exception as e:
            if espera is None or not ("UNAVAILABLE" in str(e) or ("RESOURCE_EXHAUSTED" in str(e) and "PerDay" not in str(e))):
                raise
            time.sleep(espera)
    uso["requests"] += 1
    uso["entrada"] += r.usage.prompt_tokens
    uso["salida"] += r.usage.total_tokens - r.usage.prompt_tokens
    uso["segundos"] += time.perf_counter() - t0
    return r


def costo(uso: dict) -> float:
    return (uso["entrada"] * PRECIO_USD_POR_MILLON["entrada"] + uso["salida"] * PRECIO_USD_POR_MILLON["salida"]) / 1e6


if __name__ == "__main__":
    print(ejecutar("buscar_exacta", '{"consulta": "Airflow Spark"}'))
    print(ejecutar("leer_cv", '{"id": "cv-4"}'))
    print(ejecutar("leer_cv", json.dumps({"id": ID_DE["cv-11"]}))[:300])
    lote = json.loads(ejecutar("leer_cv", '{"ids": ["cv-01", "CV-02 ", "cv-999"]}'))
    assert [c["id"] for c in lote["cvs"]] == ["cv-01", "cv-02"] and "cv-999" in lote["avisos"][0]
    assert len(json.loads(ejecutar("leer_cv", json.dumps({"ids": [f"cv-{i:02d}" for i in range(1, 10)]})))["cvs"]) == MAX_LECTURAS
    assert ejecutar("leer_cv", '{"ids": []}').startswith("Error") and ejecutar("leer_cv", '{"ids": ["cv-999"]}').startswith("Error")
    print("leer_cv batch ok")
