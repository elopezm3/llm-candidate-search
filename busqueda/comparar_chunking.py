"""Module 3: whole CV vs recursive chunks vs section chunks on the golden dataset (0 API calls: vectors are cached).
Chunks are grouped by candidate, keeping each candidate's best-scoring chunk (lesson 38), so every collection
returns a ranking of CVs and the Module 2 metrics apply unchanged.

    python3 -m busqueda.comparar_chunking
"""
import json
from statistics import mean

from .consultas import casos
from .evaluar import PROFUNDIDAD, embeber, recall_at_k, reciprocal_rank
from .indexar import COLECCIONES, DIM, MODELO, PROYECTO, cliente

SALIDA = PROYECTO / "data" / "processed" / "busqueda"


def ranking(q, coleccion: str, vector: list[float], limite: int = PROFUNDIDAD, filtro=None) -> list[tuple[str, float, str]]:
    """Top CVs as (archivo, best score, best chunk's section)."""
    grupos = q.query_points_groups(coleccion, query=vector, group_by="archivo", limit=limite, group_size=1,
                                   query_filter=filtro, with_payload=["seccion"]).groups
    return [(g.id, g.hits[0].score, g.hits[0].payload.get("seccion")) for g in grupos]


if __name__ == "__main__":
    cs = casos()
    vq = embeber("voyage", MODELO, DIM, {c["id"]: c["consulta"] for c in cs}, "query")
    q = cliente()
    resultados = {}
    print(f"{'collection':14} {'recall@5':>9} {'MRR':>6} {'r@5 hard':>9} {'r@5 easy':>9}")
    for col in COLECCIONES:
        filas = []
        for c in cs:
            r = ranking(q, col, vq[c["id"]])
            devueltos = [a for a, _, _ in r]
            filas.append({"id": c["id"], "dificultad": c["dificultad"], "recall@5": recall_at_k(devueltos, c["esperados"]),
                          "rr": reciprocal_rank(devueltos, c["esperados"]),
                          "posiciones": {e: (devueltos.index(e) + 1 if e in devueltos else None) for e in c["esperados"]},
                          "top5": [(a, round(s, 3), sec) for a, s, sec in r[:5]]})
        resultados[col] = filas
        print(f"{col:14} {mean(f['recall@5'] for f in filas):>9.2f} {mean(f['rr'] for f in filas):>6.2f} "
              f"{mean(f['recall@5'] for f in filas if f['dificultad'] == 'dificil'):>9.2f} "
              f"{mean(f['recall@5'] for f in filas if f['dificultad'] == 'facil'):>9.2f}")
    q.close()
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "chunking_comparacion.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2))
    # Cases where strategies disagree most: the ones the course says teach the most
    print("\nBiggest differences (rank of the first expected CV: whole / recursive / sections):")
    filas = {col: {f["id"]: f for f in resultados[col]} for col in COLECCIONES}
    def primero(f): return min((p for p in f["posiciones"].values() if p), default=99)
    difs = sorted(cs, key=lambda c: -max(abs(primero(filas[a][c["id"]]) - primero(filas[b][c["id"]])) for a in COLECCIONES for b in COLECCIONES))
    for c in difs[:6]:
        print(f"  {c['id']} {c.get('cargo', c['consulta'])[:45]:45} " + " / ".join(str(primero(filas[col][c['id']])) for col in COLECCIONES))
