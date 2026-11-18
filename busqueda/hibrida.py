"""Module 4: hybrid search (Voyage dense + BM25 in Spanish) fused with RRF, grouped by candidate.

Collection `cvs_hibrida` = the section chunks of Module 3 with two named vectors:
- "dense": the voyage-3-large vectors already in `cvs_secciones` (copied, not re-embedded: free);
- "bm25": FastEmbed's Qdrant/bm25 computed locally, language **spanish** and avg_len from our chunks (lessons 6–7:
  the default is English, which fails silently on Spanish CVs).

One query per branch (lesson 24): for golden postings the semantic branch gets the usual short query, BM25 only the
exact terms (technologies + study areas). Filters go at the ROOT so both branches obey them (lesson 23).

    python3 -m busqueda.hibrida             # build the collection if missing + compare dense / bm25 / hybrid (≈ USD 0)
"""
import atexit
import json
import re
from statistics import mean

from qdrant_client import models

from data_extraction.rutas import GOLDEN, SALIDA_VACANTES

from .consultas import casos
from data_extraction.extraer_cvs import anotar_costo

from .evaluar import PROFUNDIDAD, USO_VOYAGE, embeber, recall_at_k, reciprocal_rank
from .indexar import DIM, MODELO, PROYECTO, cliente

COLECCION = "cvs_hibrida"
BM25 = "Qdrant/bm25"
PREFETCH = 100  # chunks per branch before fusion: ~5x the 20 CVs we rank (lesson 23: 3–5x the final K)
SALIDA = PROYECTO / "data" / "processed" / "busqueda"


def construir(q) -> float:
    """Builds cvs_hibrida from cvs_secciones if missing; returns the avg chunk length in words (BM25's avg_len)."""
    puntos = q.scroll("cvs_secciones", limit=10_000, with_payload=True, with_vectors=True)[0]
    avg_len = mean(len(p.payload["texto"].split()) for p in puntos)
    if q.collection_exists(COLECCION) and q.count(COLECCION).count == len(puntos):
        return avg_len
    if q.collection_exists(COLECCION):
        q.delete_collection(COLECCION)
    q.create_collection(COLECCION, vectors_config={"dense": models.VectorParams(size=DIM, distance=models.Distance.COSINE)},
                        sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)})
    q.create_payload_index(COLECCION, "archivo", models.PayloadSchemaType.KEYWORD)
    q.upload_points(COLECCION, [models.PointStruct(id=p.id, payload=p.payload, vector={
        "dense": p.vector,
        "bm25": models.Document(text=p.payload["texto"], model=BM25, options={"language": "spanish", "avg_len": avg_len})})
        for p in puntos], wait=True)
    return avg_len


def buscar(q, sistema: str, vector: list[float], texto_bm25: str, avg_len: float, filtro=None, limite: int = PROFUNDIDAD) -> list[str]:
    """Ranked CVs (best chunk per CV) for sistema in {"dense", "bm25", "hibrida"}."""
    doc_bm25 = models.Document(text=texto_bm25 or " ", model=BM25, options={"language": "spanish", "avg_len": avg_len})
    comun = dict(group_by="archivo", limit=limite, group_size=1, query_filter=filtro, with_payload=False)
    if sistema == "dense":
        r = q.query_points_groups(COLECCION, query=vector, using="dense", **comun)
    elif sistema == "bm25":
        r = q.query_points_groups(COLECCION, query=doc_bm25, using="bm25", **comun)
    elif not texto_bm25.strip():  # no exact terms in the query: the BM25 branch would only add noise (lesson 18)
        r = q.query_points_groups(COLECCION, query=vector, using="dense", **comun)
    else:
        r = q.query_points_groups(COLECCION, prefetch=[models.Prefetch(query=vector, using="dense", limit=PREFETCH),
                                                       models.Prefetch(query=doc_bm25, using="bm25", limit=PREFETCH)],
                                  query=models.FusionQuery(fusion=models.Fusion.RRF), **comun)
    return [g.id for g in r.groups]


MAX_FRECUENCIA = 0.15  # a term in more than 15% of CVs (Excel, Python, SQL...) carries no "surprise" for BM25


def texto_bm25_de_vacante(v: dict, frecuencia) -> str:
    """Only RARE words from the posting's technologies. BM25 matches word by word, so rarity is per word too:
    "Microsoft Excel" looks rare as a phrase (1% of CVs) but "excel" is in 26%. Study areas and common tools made the
    BM25 ranking near-random and dragged hybrid recall below dense-only on the golden set (see DECISIONS.md)."""
    palabras = dict.fromkeys(w for t in v["tecnologias_requeridas"] + v["tecnologias_deseables"] for w in re.findall(r"[\w.+#-]+", t.lower()))
    return " ".join(w for w in palabras if frecuencia(w) <= MAX_FRECUENCIA)


def frecuencias(docs: dict[str, str]):
    """Share of CVs whose text literally contains a word."""
    from .terminos_exactos import contiene
    textos = [t.lower() for t in docs.values()]
    cache = {}
    def f(palabra: str) -> float:
        if palabra not in cache:
            cache[palabra] = sum(contiene(t, palabra) for t in textos) / len(textos)
        return cache[palabra]
    return f


def evaluar_set(q, nombre: str, cs: list[dict], textos_bm25: dict[str, str], avg_len: float) -> dict:
    vq = embeber("voyage", MODELO, DIM, {c["id"]: c["consulta"] for c in cs}, "query")
    out = {}
    for sistema in ("dense", "bm25", "hibrida"):
        filas = []
        for c in cs:
            dev = buscar(q, sistema, vq[c["id"]], textos_bm25[c["id"]], avg_len)
            filas.append({"id": c["id"], "recall@5": recall_at_k(dev, c["esperados"]), "rr": reciprocal_rank(dev, c["esperados"]),
                          "top1": dev[:1] == [e for e in dev[:1] if e in c["esperados"]] and bool(dev[:1]),
                          "n_resultados": len(dev),
                          "posiciones": {e: (dev.index(e) + 1 if e in dev else None) for e in c["esperados"]}})
        out[sistema] = filas
        print(f"  {sistema:8} top1 {mean(f['top1'] for f in filas):.2f} · recall@5 {mean(f['recall@5'] for f in filas):.2f} · "
              f"MRR {mean(f['rr'] for f in filas):.2f} · min results/query {min(f['n_resultados'] for f in filas)}")
    (SALIDA / f"hibrida_{nombre}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    atexit.register(lambda: USO_VOYAGE["requests"] and anotar_costo("Module 4: query embeddings (exact-term set)", "hibrida-v1",
                                                                    f"Voyage ({MODELO})", USO_VOYAGE["requests"], USO_VOYAGE["tokens"], 0, USO_VOYAGE["costo"]))
    q = cliente()
    avg_len = construir(q)
    print(f"{COLECCION}: {q.count(COLECCION).count} chunks · BM25 avg_len {avg_len:.0f} words (spanish)\n")
    vac = {json.loads(f.read_text())["source_file"]: json.loads(f.read_text())["vacante"] for f in SALIDA_VACANTES.glob("*.vac-v2.json")}
    golden = casos()
    from .consultas import corpus
    frec = frecuencias(corpus())
    bm25_golden = {c["id"]: texto_bm25_de_vacante(vac[c["vacante_archivo"]], frec) if c["tipo"] == "vacante" else c["consulta"] for c in golden}
    print(f"Golden dataset ({len(golden)} cases, mixed queries):")
    evaluar_set(q, "golden", golden, bm25_golden, avg_len)
    exactos = json.loads((GOLDEN / "terminos_exactos.json").read_text())
    print(f"\nExact-term set ({len(exactos)} cases):")
    res = evaluar_set(q, "exactos", exactos, {c["id"]: c["consulta"] for c in exactos}, avg_len)
    print("\nPer query, rank of the first expected CV (dense / bm25 / hybrid):")
    for c in exactos:
        r = [min((p for p in next(f for f in res[s] if f["id"] == c["id"])["posiciones"].values() if p), default="-") for s in res]
        print(f"  {c['id']} {c['consulta'][:48]:48} {r[0]!s:>3} / {r[1]!s:>3} / {r[2]!s:>3}")
    q.close()
