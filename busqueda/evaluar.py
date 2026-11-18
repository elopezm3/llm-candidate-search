"""Module 2 project: index the 97 CVs in Qdrant with each embedding configuration and measure recall@5 and MRR
on the golden dataset.

    python3 -m busqueda.evaluar local              # free local baseline (FastEmbed, runs on CPU)
    python3 -m busqueda.evaluar voyage             # dry run: configurations + estimated cost, 0 requests
    python3 -m busqueda.evaluar voyage --correr    # paid run (Voyage), logged in COSTOS.md

Embeddings are cached on disk per (model, dimension): re-running or re-evaluating never pays twice (course lesson 5).
"""
import atexit
import hashlib
import json
import sys
import time
import uuid
from statistics import mean

from qdrant_client import QdrantClient, models

from data_extraction.extraer_cvs import anotar_costo
from data_extraction.rutas import PROYECTO

from .consultas import casos, corpus

EMB = PROYECTO / "data" / "processed" / "embeddings"
SALIDA = PROYECTO / "data" / "processed" / "busqueda"
K = 5          # recall@5
PROFUNDIDAD = 20  # ranks looked at for MRR; a first hit below 20 counts as 0

# USD per 1M tokens, Voyage list prices as given in the course (Module 2, lesson 19, Sept 2026).
PRECIO_VOYAGE = {"voyage-3-large": 0.18, "voyage-3.5": 0.06, "voyage-3.5-lite": 0.02}
CONFIGS = {
    "local": [("fastembed", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", 384)],
    "voyage": [("voyage", m, d) for m in PRECIO_VOYAGE for d in (1024, 512, 256)],
}
USO_VOYAGE = {"requests": 0, "tokens": 0, "costo": 0.0}


def _cache(modelo: str, dim: int, tipo: str) -> dict:
    f = EMB / f"{modelo.replace('/', '__')}.{dim}.{tipo}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def _guardar(modelo: str, dim: int, tipo: str, datos: dict) -> None:
    EMB.mkdir(parents=True, exist_ok=True)
    (EMB / f"{modelo.replace('/', '__')}.{dim}.{tipo}.json").write_text(json.dumps(datos))


def _voyage(textos: list[str], modelo: str, dim: int, input_type: str) -> list[list[float]]:
    import voyageai
    cliente = voyageai.Client(max_retries=0)
    vectores, lote, chars = [], [], 0
    lotes = []
    for t in textos:  # batches of ≤ 32 texts and ≤ ~60k tokens
        if lote and (len(lote) == 32 or chars + len(t) > 240_000):
            lotes.append(lote); lote, chars = [], 0
        lote.append(t); chars += len(t)
    lotes.append(lote)
    for b in lotes:
        for espera in (30, 90, None):
            try:
                r = cliente.embed(b, model=modelo, input_type=input_type, output_dimension=dim, truncation=False)
                break
            except Exception as e:
                if espera is None or "rate" not in str(e).lower():
                    raise
                print(f"    Voyage rate limit, waiting {espera}s…", flush=True)
                time.sleep(espera)
        USO_VOYAGE["requests"] += 1
        USO_VOYAGE["tokens"] += r.total_tokens
        USO_VOYAGE["costo"] += r.total_tokens * PRECIO_VOYAGE[modelo] / 1e6
        vectores += r.embeddings
    return vectores


def _fastembed(textos: list[str], modelo: str) -> list[list[float]]:
    from fastembed import TextEmbedding
    return [v.tolist() for v in TextEmbedding(modelo).embed(textos, batch_size=16)]


def embeber(proveedor: str, modelo: str, dim: int, textos: dict[str, str], tipo: str) -> dict[str, list[float]]:
    """tipo = 'document' (CVs) or 'query'. Only texts missing from the cache are sent."""
    cache = _cache(modelo, dim, tipo)
    clave = (lambda k, t: k) if tipo == "document" else (lambda k, t: hashlib.sha1(t.encode()).hexdigest())
    faltan = {k: t for k, t in textos.items() if clave(k, t) not in cache}
    if faltan:
        print(f"  embedding {len(faltan)} {'queries' if tipo == 'query' else 'documents'} with {modelo} @ {dim}", flush=True)
        vecs = _voyage(list(faltan.values()), modelo, dim, tipo) if proveedor == "voyage" else _fastembed(list(faltan.values()), modelo)
        cache.update({clave(k, t): v for (k, t), v in zip(faltan.items(), vecs)})
        _guardar(modelo, dim, tipo, cache)
    return {k: cache[clave(k, t)] for k, t in textos.items()}


def recall_at_k(devueltos: list[str], esperados: list[str], k: int = K) -> float:
    return sum(e in devueltos[:k] for e in esperados) / len(esperados)


def reciprocal_rank(devueltos: list[str], esperados: list[str]) -> float:
    return next((1 / i for i, a in enumerate(devueltos, 1) if a in esperados), 0.0)


def evaluar(proveedor: str, modelo: str, dim: int, docs: dict[str, str], cs: list[dict]) -> dict:
    vec_docs = embeber(proveedor, modelo, dim, docs, "document")
    vec_q = embeber(proveedor, modelo, dim, {c["id"]: c["consulta"] for c in cs}, "query")
    q = QdrantClient(":memory:")
    q.create_collection("cvs", vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE))
    # Stable IDs derived from the file name (lesson 27): re-indexing replaces instead of duplicating.
    q.upload_points("cvs", [models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, a)), vector=v, payload={"archivo": a})
                            for a, v in vec_docs.items()], wait=True)
    filas = []
    for c in cs:
        devueltos = [p.payload["archivo"] for p in q.query_points("cvs", query=vec_q[c["id"]], limit=PROFUNDIDAD).points]
        filas.append({"id": c["id"], "dificultad": c["dificultad"], "recall@5": recall_at_k(devueltos, c["esperados"]),
                      "rr": reciprocal_rank(devueltos, c["esperados"]),
                      "posiciones": {e: (devueltos.index(e) + 1 if e in devueltos else None) for e in c["esperados"]},
                      "top5": devueltos[:K]})
    return {"modelo": modelo, "dim": dim, "recall@5": mean(f["recall@5"] for f in filas), "mrr": mean(f["rr"] for f in filas),
            "recall@5_dificil": mean(f["recall@5"] for f in filas if f["dificultad"] == "dificil"),
            "recall@5_facil": mean(f["recall@5"] for f in filas if f["dificultad"] == "facil"), "casos": filas}


if __name__ == "__main__":
    grupo = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in CONFIGS else "local"
    configs, docs, cs = CONFIGS[grupo], corpus(), casos()
    if grupo == "voyage":
        tokens = sum(map(len, docs.values())) // 4
        pendientes = [(m, d) for _, m, d in configs if len(_cache(m, d, "document")) < len(docs)]
        estimado = sum(tokens * PRECIO_VOYAGE[m] / 1e6 for m, _ in pendientes)
        print(f"{len(configs)} configurations, {len(pendientes)} not cached · corpus ≈ {tokens:,} tokens → estimate ≈ USD {estimado:.3f}")
        if "--correr" not in sys.argv:
            print("Dry run. Add --correr to embed with Voyage (paid).")
            sys.exit()
        atexit.register(lambda: USO_VOYAGE["requests"] and anotar_costo(
            "Module 2: embeddings for the golden-dataset eval", "golden-v1", "Voyage (" + ", ".join(sorted(PRECIO_VOYAGE)) + ")",
            USO_VOYAGE["requests"], USO_VOYAGE["tokens"], 0, USO_VOYAGE["costo"]))
    SALIDA.mkdir(parents=True, exist_ok=True)
    print(f"\n{'model':58} {'dim':>5} {'recall@5':>9} {'MRR':>6} {'r@5 hard':>9} {'r@5 easy':>9}")
    for proveedor, modelo, dim in configs:
        r = evaluar(proveedor, modelo, dim, docs, cs)
        (SALIDA / f"{modelo.replace('/', '__')}.{dim}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2))
        print(f"{modelo:58} {dim:>5} {r['recall@5']:>9.2f} {r['mrr']:>6.2f} {r['recall@5_dificil']:>9.2f} {r['recall@5_facil']:>9.2f}", flush=True)
    if USO_VOYAGE["requests"]:
        print(f"\nVoyage: {USO_VOYAGE['requests']} requests · {USO_VOYAGE['tokens']:,} tokens · ≈ USD {USO_VOYAGE['costo']:.4f}")
