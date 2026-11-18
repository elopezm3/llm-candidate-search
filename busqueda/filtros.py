"""Module 3: does filtering on the posting's hard requirements help? (0 API calls: vectors are cached)

For every golden posting that states minimum years, minimum education or English, search the sections collection
without a filter, with a strict filter and with a tolerant one (80% of the years), filtering INSIDE the query
(never post-filtering, lesson 28). CVs whose model-made field is missing are kept, not excluded.

    python3 -m busqueda.filtros
"""
import json
from statistics import mean

from qdrant_client import models

from data_extraction.rutas import SALIDA_VACANTES

from .comparar_chunking import ranking
from .consultas import casos
from .evaluar import embeber, recall_at_k, reciprocal_rank
from .indexar import DIM, MODELO, NIVELES, cliente

COLECCION = "cvs_secciones"
NIVELES_IDIOMA = ["A1", "A2", "B1", "B2", "C1", "C2", "nativo"]


def _o_desconocido(campo: str, condicion: models.FieldCondition) -> models.Filter:
    """Meets the condition OR the field is unknown: missing model data must not exclude a candidate."""
    return models.Filter(should=[condicion, models.IsNullCondition(is_null=models.PayloadField(key=campo)),
                                 models.IsEmptyCondition(is_empty=models.PayloadField(key=campo))])


def filtro(v: dict, tolerancia: float = 1.0) -> models.Filter | None:
    must = []
    if v["anos_experiencia_min"]:
        must.append(_o_desconocido("anos_experiencia", models.FieldCondition(
            key="anos_experiencia", range=models.Range(gte=v["anos_experiencia_min"] * tolerancia))))
    if v["nivel_educativo_min"] and v["nivel_educativo_min"] != "curso":
        # nivel_educativo_rango = -1 means "no degree extracted" (unknown), which must not count as "below the minimum"
        must.append(models.Filter(should=[
            models.FieldCondition(key="nivel_educativo_rango", range=models.Range(gte=NIVELES.index(v["nivel_educativo_min"]))),
            models.FieldCondition(key="nivel_educativo_rango", match=models.MatchValue(value=-1))]))
    ingles = next((i["nivel"] for i in v["idiomas"] if i["idioma"].lower().startswith("ingl") and i["nivel"] and i.get("obligatorio", True)), None)
    if ingles:
        validos = NIVELES_IDIOMA[NIVELES_IDIOMA.index(ingles):]
        if tolerancia < 1:
            validos = NIVELES_IDIOMA[max(0, NIVELES_IDIOMA.index(ingles) - 1):]  # tolerant: one CEFR level below
        must.append(_o_desconocido("ingles", models.FieldCondition(key="ingles", match=models.MatchAny(any=validos))))
    return models.Filter(must=must) if must else None


if __name__ == "__main__":
    vac = {json.loads(f.read_text())["source_file"]: json.loads(f.read_text())["vacante"] for f in SALIDA_VACANTES.glob("*.vac-v2.json")}
    cs = [c for c in casos() if c["tipo"] == "vacante" and filtro(vac[c["vacante_archivo"]])]
    vq = embeber("voyage", MODELO, DIM, {c["id"]: c["consulta"] for c in cs}, "query")
    q = cliente()
    variantes = {"no filter": None, "strict": 1.0, "tolerant (80%)": 0.8}
    res = {k: [] for k in variantes}
    excluidos = {k: [] for k in variantes}
    for c in cs:
        v = vac[c["vacante_archivo"]]
        for nombre, tol in variantes.items():
            f = filtro(v, tol) if tol else None
            devueltos = [a for a, _, _ in ranking(q, COLECCION, vq[c["id"]], filtro=f)]
            res[nombre].append((c, recall_at_k(devueltos, c["esperados"]), reciprocal_rank(devueltos, c["esperados"])))
            if f:  # expected candidates the filter itself removes from the whole collection
                pasan = {p.payload["archivo"] for p in q.scroll(COLECCION, scroll_filter=f, limit=10_000, with_payload=["archivo"])[0]}
                excluidos[nombre] += [(c["id"], e) for e in c["esperados"] if e not in pasan]
    q.close()
    print(f"{len(cs)} golden postings with hard requirements (years / education / English), collection {COLECCION}\n")
    print(f"{'variant':16} {'recall@5':>9} {'MRR':>6}  expected CVs the filter removes")
    for nombre in variantes:
        print(f"{nombre:16} {mean(r for _, r, _ in res[nombre]):>9.2f} {mean(m for _, _, m in res[nombre]):>6.2f}  "
              f"{len(excluidos[nombre])}: {[(i, e.replace('_CV', '').rsplit('.', 1)[0][:20]) for i, e in excluidos[nombre]][:6]}")
