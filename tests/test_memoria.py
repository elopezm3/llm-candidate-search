"""Module 8: episodic memory without API calls (fake embeddings)."""
import json

from busqueda import memoria
from busqueda.borrar import Persona, _limpiar


def test_episodios(tmp_path, monkeypatch):
    monkeypatch.setattr(memoria, "EPISODIOS", tmp_path / "episodios.json")
    vecs = {"analista de procesos": [1, 0], "ingeniero de IA": [0, 1], "analista de mejora continua": [0.9, 0.1]}
    monkeypatch.setattr(memoria, "embeber", lambda *a: {k: vecs[t] for k, t in a[3].items()})
    memoria.guardar_episodio("V03", "analista de procesos", ["cv-86"], {"cv-51": "viene de datos, no de procesos", "cv-09": " "})
    memoria.guardar_episodio("V03", "analista de procesos", ["cv-86"], {"cv-51": "viene de datos, no de procesos"})
    memoria.guardar_episodio("V01", "ingeniero de IA", [], {"cv-73": "poca experiencia real en IA"})
    eps = memoria.cargar()
    assert len(eps) == 2 and eps["V03"]["quitados"] == {"cv-51": "viene de datos, no de procesos"}  # idempotent, empty reason dropped
    s = memoria.similares("analista de mejora continua")
    assert [c for _, c, _ in s] == ["V03", "V01"]                       # most similar posting first
    assert [c for _, c, _ in memoria.similares("analista de mejora continua", excluir="V03")] == ["V01"]
    texto = memoria.como_ejemplos(s[:1])
    assert 'Descartó cv-51: "viene de datos, no de procesos"' in texto and "no instrucciones" in texto
    limpio = _limpiar(eps, Persona("X_CV.pdf", "Nombre Falso", "cv-51"))  # deleting cv-51 removes it from the episode
    assert "cv-51" not in json.dumps(limpio) and limpio["V03"]["aprobados"] == ["cv-86"]
