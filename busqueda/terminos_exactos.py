"""Module 4 eval set: exact-term queries with OBJECTIVE labels (course lesson 27 shape).
Expected CVs = the ones whose full text literally contains ALL the query's key terms; nobody's judgement involved.
Note: literal labels favour BM25 by construction, which is exactly the question here: does it find exact terms that
semantic search misses?

    python3 -m busqueda.terminos_exactos   # writes data/golden/terminos_exactos.json (0 API calls)
"""
import json
import re

from data_extraction.rutas import GOLDEN

from .consultas import corpus

# (id, kind, recruiter query, key terms that must ALL appear literally)
CONSULTAS = [
    ("E01", "herramienta", "Candidato que haya construido agentes con CrewAI", ["crewai"]),
    ("E02", "herramienta", "Experiencia con Apache Spark y Airflow", ["spark", "airflow"]),
    ("E03", "herramienta", "Ingeniero civil que use PLAXIS para geotecnia", ["plaxis"]),
    ("E04", "certificacion", "Conocimiento de SARLAFT y SAGRILAFT para cumplimiento", ["sarlaft", "sagrilaft"]),
    ("E05", "herramienta", "Modelado de procesos de negocio con Bizagi", ["bizagi"]),
    ("E06", "herramienta", "Búsqueda vectorial con Pinecone y OpenSearch", ["pinecone", "opensearch"]),
    ("E07", "herramienta", "Simulación de sistemas con Modelica y Dymola", ["modelica", "dymola"]),
    ("E08", "herramienta", "Geólogo que maneje Vulcan y MapInfo", ["vulcan", "mapinfo"]),
    ("E09", "herramienta", "Pruebas end-to-end automatizadas con Cypress", ["cypress"]),
    ("E10", "herramienta", "Agentes con LangGraph", ["langgraph"]),
    ("U01", "nombre_unico", "Ha trabajado en Skalo Tek", ["skalo tek"]),
    ("U02", "nombre_unico", "Experiencia en D&T Proyectos", ["d&t proyectos"]),
    ("U03", "nombre_unico", "Trabajó en la Corporación Social Fragua", ["fragua"]),
    ("M01", "mixta", "Ingeniero de datos con experiencia en Azure Data Factory", ["azure data factory"]),
    ("M02", "mixta", "Desarrollador web full stack con Vue.js y CakePHP", ["vue.js", "cakephp"]),
]


def contiene(texto: str, termino: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(termino)}(?![a-z0-9])", texto) is not None


if __name__ == "__main__":
    docs = {a: t.lower() for a, t in corpus().items()}
    casos = []
    for cid, tipo, consulta, terminos in CONSULTAS:
        esperados = sorted(a for a, t in docs.items() if all(contiene(t, x) for x in terminos))
        assert 1 <= len(esperados) <= 3, (cid, terminos, esperados)  # rare enough to be a real exact-term test
        casos.append({"id": cid, "tipo": tipo, "consulta": consulta, "terminos": terminos, "esperados": esperados,
                      "dificultad": "exacto"})
        print(f"{cid} {consulta[:50]:50} → {[e.replace('_CV', '').rsplit('.', 1)[0][:22] for e in esperados]}")
    (GOLDEN / "terminos_exactos.json").write_text(json.dumps(casos, ensure_ascii=False, indent=2))
    print(f"\n{len(casos)} exact-term cases → data/golden/terminos_exactos.json")
