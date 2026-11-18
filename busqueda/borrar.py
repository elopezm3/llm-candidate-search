"""Module 8: delete a candidate EVERYWHERE (Ley 1581 art. 8, right to deletion; art. 14-15: answer within 10-15 business
days, so it must be one command, not a manual hunt), then verify nothing is left.

    python3 -m busqueda.borrar cv-11                # dry run: where does this person appear?
    python3 -m busqueda.borrar cv-11 --confirmar    # deletes, then runs the inventory again: it must come back empty

Where a candidate lives (found by grepping data/, more places than the course lists):
  files       raw PDF, extractions (every schema version), sample runs, highlighted PDF, contact drafts
  Qdrant      their chunks in the 4 collections
  caches      their document embeddings (keys "archivo" or "archivo#pos#hash")
  checkpoints LangGraph threads whose saved state mentions them (the whole thread goes)
  JSON        evaluation outputs and golden sets: list items that ARE them are dropped, mentions become "[borrado]"
  Langfuse    traces that mention them (names are not masked, by design)
  docs        *.md notes in the project: reported for manual review, never edited automatically
The ids map keeps "_borrado_cv-NN" so the number is never reused (an old trace "cv-11" can't point at someone new).
"""
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

from data_extraction.rutas import PROYECTO

BORRADO = "[borrado]"


class Persona:
    def __init__(self, archivo: str, nombre: str, cid: str):
        self.archivo, self.nombre, self.cid = archivo, nombre, cid
        self.stem = archivo.rsplit(".", 1)[0]
        self.patron = re.compile("|".join([re.escape(archivo), re.escape(self.stem), re.escape(nombre), rf"\b{cid}\b"]))

    def en(self, texto: str) -> bool:
        return bool(self.patron.search(texto))


def _archivos(d: Path, p: Persona) -> list[Path]:
    globs = [("raw/CVs", p.archivo), ("processed/cvs", f"{p.stem}.*"), ("processed/muestra", f"{p.stem}.*"),
             ("samples", f"{p.stem}.*"), ("samples", f"{p.stem}_*"), ("processed/resaltados", f"{p.stem}_resaltado.pdf"),
             ("processed/contacto", f"*_{p.cid}.md")]
    return sorted({f for sub, g in globs for f in (d / sub).glob(g)})


def _json(d: Path) -> list[Path]:
    return sorted([f for sub in ("golden", "processed/busqueda", "processed/rag") for f in (d / sub).rglob("*.json*")]
                  + list((d / "processed").glob("episodios.json")))  # Module 8 episodes name candidates too


def _limpiar(x, p: Persona):
    """Drops list items / dict keys that ARE the person; redacts mentions inside other strings."""
    if isinstance(x, str):
        return p.patron.sub(BORRADO, x)
    if isinstance(x, list):
        return [_limpiar(v, p) for v in x if not (isinstance(v, str) and v in (p.archivo, p.cid))]
    if isinstance(x, dict):
        return {k: _limpiar(v, p) for k, v in x.items() if k not in (p.archivo, p.cid) and not k.startswith(p.archivo + "#")}
    return x


def _hilos(d: Path, p: Persona) -> list[str]:
    ruta = d / "checkpoints.sqlite"
    if not ruta.exists():
        return []
    claves = [s.encode() for s in (p.archivo, p.nombre, p.cid)]
    with sqlite3.connect(ruta) as c:
        filas = c.execute("select thread_id, checkpoint, metadata from checkpoints union all "
                          "select thread_id, value, '' from writes").fetchall()
    return sorted({t for t, *blobs in filas if any(k in (b if isinstance(b, bytes) else str(b).encode()) for b in blobs for k in claves)})


def _trazas(p: Persona, langfuse) -> list[str]:
    ids, cursor = set(), None
    while True:
        r = langfuse.api.observations.get_many(limit=500, fields="core,io", cursor=cursor)
        ids |= {o.trace_id for o in r.data if p.en(f"{o.input} {o.output}")}
        cursor = r.meta.cursor if r.data else None
        if not cursor:
            return sorted(ids)


def inventario(d: Path, p: Persona, qdrant, langfuse=None) -> dict[str, list]:
    from qdrant_client import models
    filtro = models.Filter(must=[models.FieldCondition(key="archivo", match=models.MatchValue(value=p.archivo))])
    cache = {f.name: n for f in (d / "processed/embeddings").glob("*.document.json")
             if (n := sum(k == p.archivo or k.startswith(p.archivo + "#") for k in json.loads(f.read_text())))}
    return {
        "files": [str(f.relative_to(d)) for f in _archivos(d, p)],
        "qdrant": [f"{c.name}: {n} chunks" for c in qdrant.get_collections().collections
                   if (n := qdrant.count(c.name, count_filter=filtro, exact=True).count)],
        "embeddings cache": [f"{k}: {n}" for k, n in cache.items()],
        "checkpoints": _hilos(d, p),
        "json": [str(f.relative_to(d)) for f in _json(d) if p.en(f.read_text())],
        "langfuse": _trazas(p, langfuse) if langfuse else [],
        "ids": [p.archivo] if p.archivo in json.loads((d / "processed/ids.json").read_text()) else [],
        "docs (manual review)": [f.name for f in PROYECTO.glob("*.md") if p.en(f.read_text())],
    }


def borrar(d: Path, p: Persona, qdrant, langfuse=None) -> None:
    from langgraph.checkpoint.sqlite import SqliteSaver
    from qdrant_client import models
    for f in _archivos(d, p):
        f.unlink()
    filtro = models.Filter(must=[models.FieldCondition(key="archivo", match=models.MatchValue(value=p.archivo))])
    for c in qdrant.get_collections().collections:
        qdrant.delete(c.name, points_selector=models.FilterSelector(filter=filtro), wait=True)
    for f in (d / "processed/embeddings").glob("*.document.json"):
        cache = json.loads(f.read_text())
        limpio = {k: v for k, v in cache.items() if not (k == p.archivo or k.startswith(p.archivo + "#"))}
        if len(limpio) != len(cache):
            f.write_text(json.dumps(limpio))
    if hilos := _hilos(d, p):
        with sqlite3.connect(d / "checkpoints.sqlite", check_same_thread=False) as c:
            for t in hilos:
                SqliteSaver(c).delete_thread(t)
    for f in _json(d):
        if p.en(f.read_text()):
            if f.suffix == ".jsonl":
                f.write_text("".join(json.dumps(_limpiar(json.loads(l), p), ensure_ascii=False) + "\n" for l in f.read_text().splitlines() if l.strip()))
            else:
                datos = _limpiar(json.loads(f.read_text()), p)
                if f.parent.name == "golden" and isinstance(datos, list):  # a case left with no expected answer can't be scored
                    datos = [c for c in datos if not (isinstance(c, dict) and "esperados" in c and not c["esperados"])]
                f.write_text(json.dumps(datos, ensure_ascii=False, indent=2))
    ids = json.loads((d / "processed/ids.json").read_text())
    if p.archivo in ids:
        ids[f"_borrado_{ids.pop(p.archivo)}"] = p.cid
        (d / "processed/ids.json").write_text(json.dumps(ids, ensure_ascii=False, indent=1))
    for t in _trazas(p, langfuse) if langfuse else []:
        langfuse.api.trace.delete(t)


def pendiente(inv: dict) -> dict:
    return {k: v for k, v in inv.items() if v and k != "docs (manual review)"}


def persona(cid: str) -> Persona:
    from .herramientas import ARCHIVO_DE, _CVS
    archivo = ARCHIVO_DE[cid]
    return Persona(archivo, _CVS[archivo]["cv"]["nombre_completo"], cid)


def mostrar(inv: dict) -> None:
    for k, v in inv.items():
        print(f"  {k:22} {len(v):3}  {', '.join(map(str, v[:4]))}{' …' if len(v) > 4 else ''}")


if __name__ == "__main__":
    from .indexar import cliente
    from .observabilidad import langfuse
    p = persona(sys.argv[1].lower())
    d = PROYECTO / "data"
    q = cliente()
    print(f"{p.cid} = {p.nombre} ({p.archivo})")
    inv = inventario(d, p, q, langfuse)
    mostrar(inv)
    if "--confirmar" not in sys.argv:
        print("\nDry run: nothing deleted. Add --confirmar to delete.")
        q.close()
        sys.exit()
    borrar(d, p, q, langfuse)
    for _ in range(20):  # Langfuse deletes asynchronously
        inv = inventario(d, p, q, langfuse)
        if not pendiente(inv):
            break
        time.sleep(3)
    print("\nAfter deleting:")
    mostrar(inv)
    print("VERIFIED: nothing left" if not pendiente(inv) else f"STILL PRESENT: {pendiente(inv)}")
    q.close()
