"""Module 3: persistent Qdrant collections (data/qdrant/) reused by Modules 4-8.

    cvs_completo   one vector per whole CV (embeddings reused from the Module 2 cache: free)
    cvs_recursivo  ~500-token chunks, 10% overlap
    cvs_secciones  chunks by CV section, title prepended

    python3 -m busqueda.indexar            # dry run: chunks + tokens still to embed + estimated cost
    python3 -m busqueda.indexar --correr   # embeds with Voyage (paid, logged in COSTOS.md) and syncs Qdrant

Payload per point:
- from the file (always right, safe to filter on): archivo, seccion, posicion, n_chunks, doc_hash, fecha_archivo;
- from the Module 1 extraction (model-made, reviewed on samples): anos_experiencia, nivel_educativo, idiomas, ingles, tecnologias.
The unit of update is the document (lesson 26): a CV whose hash changed has all its chunks deleted, then re-inserted.
"""
import atexit
import hashlib
import json
import sys
import uuid
from datetime import date

from qdrant_client import QdrantClient, models

from data_extraction.extraer_cvs import anotar_costo
from data_extraction.rutas import CVS, PROYECTO, SALIDA_CVS

from .chunking import ESTRATEGIAS, tokens
from .consultas import corpus
from .evaluar import PRECIO_VOYAGE, USO_VOYAGE, _cache, embeber

QDRANT = PROYECTO / "data" / "qdrant"
MODELO, DIM = "voyage-3-large", 1024
NIVELES = ["curso", "bachiller", "tecnico", "tecnologo", "pregrado", "especializacion", "maestria", "doctorado"]
COLECCIONES = ["cvs_completo", "cvs_recursivo", "cvs_secciones"]


def cliente() -> QdrantClient:
    return QdrantClient(path=str(QDRANT))


def metadata_modelo() -> dict[str, dict]:
    """Per-CV fields from the Module 1 extraction (made by a model: enrich and filter only after review)."""
    out = {}
    for f in SALIDA_CVS.glob("*.cv-v8.json"):
        if f.name.startswith("_"):
            continue
        r = json.loads(f.read_text())
        cv = r["cv"]
        niveles = [NIVELES.index(e["nivel"]) for e in cv["educacion"] if e["nivel"] != "curso"]
        ingles = next((i["nivel"] for i in cv["idiomas"] if i["idioma"].lower().startswith("ingl")), None)
        out[r["source_file"]] = {
            "anos_experiencia": r["anos_experiencia"],
            "nivel_educativo": NIVELES[max(niveles)] if niveles else None,
            "nivel_educativo_rango": max(niveles) if niveles else -1,  # numeric, for range filters
            "ingles": ingles,
            "idiomas": [i["idioma"] for i in cv["idiomas"]],
            "tecnologias": sorted({t.lower() for t in cv["tecnologias"]}),
        }
    return out


def chunks(estrategia: str, docs: dict[str, str]) -> dict[str, list[dict]]:
    if estrategia == "cvs_completo":
        return {a: [{"seccion": None, "texto": t}] for a, t in docs.items()}
    return {a: ESTRATEGIAS[estrategia.removeprefix("cvs_")](t) for a, t in docs.items()}


def _clave(archivo: str, pos: int, texto: str) -> str:
    return f"{archivo}#{pos}#{hashlib.sha1(texto.encode()).hexdigest()[:10]}"


def sincronizar(estrategia: str, docs: dict[str, str], meta: dict, q: QdrantClient) -> tuple[int, int]:
    """Re-indexes only CVs whose content hash changed. Returns (CVs re-indexed, points in the collection)."""
    if not q.collection_exists(estrategia):
        q.create_collection(estrategia, vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE))
        q.create_payload_index(estrategia, "archivo", models.PayloadSchemaType.KEYWORD)
    actuales = {}
    for p in q.scroll(estrategia, limit=10_000, with_payload=["archivo", "doc_hash"])[0]:
        actuales[p.payload["archivo"]] = p.payload["doc_hash"]
    por_cv = chunks(estrategia, docs)
    cambiados = [a for a, t in docs.items() if actuales.get(a) != hashlib.sha256(t.encode()).hexdigest()[:16]]
    textos = {_clave(a, i, c["texto"]): c["texto"] for a in cambiados for i, c in enumerate(por_cv[a])}
    vecs = embeber("voyage", MODELO, DIM, textos, "document") if estrategia != "cvs_completo" else \
        embeber("voyage", MODELO, DIM, {a: docs[a] for a in cambiados}, "document")
    for a in cambiados:
        q.delete(estrategia, points_selector=models.FilterSelector(filter=models.Filter(
            must=[models.FieldCondition(key="archivo", match=models.MatchValue(value=a))])))
        doc_hash = hashlib.sha256(docs[a].encode()).hexdigest()[:16]
        fecha = date.fromtimestamp((CVS / a).stat().st_mtime).isoformat()
        puntos = []
        for i, c in enumerate(por_cv[a]):
            v = vecs[a] if estrategia == "cvs_completo" else vecs[_clave(a, i, c["texto"])]
            puntos.append(models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{a}#{i}")), vector=v,
                payload={"archivo": a, "seccion": c["seccion"], "posicion": i, "n_chunks": len(por_cv[a]),
                         "doc_hash": doc_hash, "fecha_archivo": fecha, "texto": c["texto"], **meta.get(a, {})}))
        q.upsert(estrategia, puntos, wait=True)
    return len(cambiados), q.count(estrategia).count


if __name__ == "__main__":
    docs, meta = corpus(), metadata_modelo()
    cache = _cache(MODELO, DIM, "document")
    pendiente = 0
    for e in COLECCIONES:
        por_cv = chunks(e, docs)
        claves = list(docs) if e == "cvs_completo" else [_clave(a, i, c["texto"]) for a, cs in por_cv.items() for i, c in enumerate(cs)]
        falt = sum(tokens(docs[k] if e == "cvs_completo" else next(c["texto"] for c in [por_cv[k.split("#")[0]][int(k.split("#")[1])]]))
                   for k in claves if k not in cache)
        pendiente += falt
        print(f"{e:14} {sum(map(len, por_cv.values())):4} points · ≈ {falt:,} tokens not yet embedded")
    print(f"estimate ≈ USD {pendiente * PRECIO_VOYAGE[MODELO] / 1e6:.3f} ({MODELO} @ {DIM})")
    if "--correr" not in sys.argv:
        print("Dry run. Add --correr to embed (paid) and sync Qdrant.")
        sys.exit()
    atexit.register(lambda: USO_VOYAGE["requests"] and anotar_costo(
        "Module 3: chunk embeddings (recursive + sections)", "chunks-v1", f"Voyage ({MODELO} @ {DIM})",
        USO_VOYAGE["requests"], USO_VOYAGE["tokens"], 0, USO_VOYAGE["costo"]))
    q = cliente()
    for e in COLECCIONES:
        n, total = sincronizar(e, docs, meta, q)
        print(f"{e:14} re-indexed {n} CVs · {total} points in collection")
    q.close()
    if USO_VOYAGE["requests"]:
        print(f"Voyage: {USO_VOYAGE['requests']} requests · {USO_VOYAGE['tokens']:,} tokens · ≈ USD {USO_VOYAGE['costo']:.4f}")
