"""Module 8: deletes a REAL candidate from a COPY of data/ (the real data is never touched) and checks that
(1) nothing of them is left and (2) every other candidate is intact. Langfuse is left out here: deleting a trace was
verified on a throwaway trace, and running it here would delete real traces.

    cd project && python3 -m pytest -q tests/test_borrar.py
"""
import json
import shutil

from qdrant_client import QdrantClient

from busqueda.borrar import borrar, inventario, pendiente, persona
from data_extraction.rutas import PROYECTO


def test_borrar_candidato_en_copia(tmp_path):
    d = tmp_path / "data"
    shutil.copytree(PROYECTO / "data", d)
    p = persona("cv-11")
    q = QdrantClient(path=str(d / "qdrant"))
    try:
        antes = inventario(d, p, q)
        assert len(pendiente(antes)) >= 6, antes            # it really was everywhere
        totales = {c.name: q.count(c.name, exact=True).count for c in q.get_collections().collections}
        suyos = {s.split(":")[0]: int(s.split(": ")[1].split()[0]) for s in antes["qdrant"]}
        otros_cvs = {f.name for f in (d / "processed/cvs").glob("*")} - {f.split("/")[-1] for f in antes["files"]}

        borrar(d, p, q)

        assert pendiente(inventario(d, p, q)) == {}         # nothing of them left
        for c, n in totales.items():                         # everyone else's chunks intact
            assert q.count(c, exact=True).count == n - suyos.get(c, 0)
        assert {f.name for f in (d / "processed/cvs").glob("*")} == otros_cvs
        golden = json.loads((d / "golden/golden_dataset.json").read_text())
        assert p.archivo not in json.dumps(golden) and len(golden) == len(json.loads((PROYECTO / "data/golden/golden_dataset.json").read_text()))
        ids = json.loads((d / "processed/ids.json").read_text())
        assert ids["_borrado_cv-11"] == "cv-11" and "cv-11" not in [v for k, v in ids.items() if not k.startswith("_")]
    finally:
        q.close()
    assert (PROYECTO / "data/raw/CVs" / p.archivo).exists()  # the real data was not touched
