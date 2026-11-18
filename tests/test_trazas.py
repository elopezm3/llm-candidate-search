"""Lesson 25: a test for the tracing itself (no server, no API calls, < 1 s once imports are warm).
Same Langfuse client and SAME production mask as the real runs; spans go to an in-memory exporter.

    cd project && python3 -m pytest -q tests/test_trazas.py
"""
import os
from types import SimpleNamespace

os.environ["LANGFUSE_TEST_EXPORT"] = "1"           # must be set BEFORE importing anything traced
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-test")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-test")

from busqueda import herramientas, workflow_lg      # noqa: E402
from busqueda.observabilidad import EXPORTADOR, langfuse  # noqa: E402
from busqueda.trazar import con_traza, revisar_trayectoria  # noqa: E402

CV = sorted(herramientas.ID_DE)[0]
CASO = {"id": "T01", "tipo": "consulta", "consulta": "Busco a quien escribió desde ana.perez@correo.co o el 300 111 22 33",
        "esperados": [CV]}


def _respuesta_falsa(*args, **kwargs):
    msg = SimpleNamespace(content=f"{herramientas.ID_DE[CV]}: encaja", tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=SimpleNamespace(prompt_tokens=120, total_tokens=150))


def _correr(monkeypatch):
    monkeypatch.setattr(herramientas, "_llamar_llm", lambda m, uso, h=None: (uso.update(requests=uso["requests"] + 1), _respuesta_falsa())[1])
    monkeypatch.setattr(herramientas, "_cliente", lambda: (None, 100.0))
    monkeypatch.setattr(herramientas, "embeber", lambda *a, **k: {a[3] and next(iter(a[3])): [0.0]})
    monkeypatch.setattr(herramientas, "_buscar", lambda *a, **k: [CV])
    EXPORTADOR.clear()
    con_traza("workflow", CASO, lambda: workflow_lg.correr(CASO, None))
    langfuse.flush()
    return [(s.name, dict(s.attributes)) for s in EXPORTADOR.get_finished_spans()]  # list: node and generation share names


def test_spans_y_tipos(monkeypatch):
    spans = dict(_correr(monkeypatch))
    for nombre in ("workflow", "preparar", "buscar", "buscar_hibrida", "explicar"):
        assert nombre in spans, sorted(spans)
    assert spans["buscar_hibrida"]["langfuse.observation.type"] == "retriever"
    assert spans["workflow"]["langfuse.observation.type"] == "chain"


def test_generation_con_modelo_uso_y_sesion(monkeypatch):
    spans = _correr(monkeypatch)
    gen = next(a for _, a in spans if a.get("langfuse.observation.type") == "generation")
    assert gen["langfuse.observation.model.name"]
    assert '"input": 120' in gen["langfuse.observation.usage_details"]
    raiz = dict(spans)["workflow"]
    assert raiz.get("user.id") == "reclutador-demo" and raiz.get("session.id") == "vacante-T01"


def test_datos_personales_enmascarados(monkeypatch):
    spans = _correr(monkeypatch)
    todo = " ".join(str(v) for _, a in spans for v in a.values())
    assert "ana.perez@correo.co" not in todo and "300 111 22 33" not in todo
    assert "[CORREO]" in todo and "[CELULAR]" in todo


def test_reglas_de_fallas_silenciosas():
    assert revisar_trayectoria(["leer_cv(x)"] * 3)[0].startswith("same call 3x")
    assert any("unexpected" in a for a in revisar_trayectoria(["get_weather(y)"]))
    assert revisar_trayectoria(["buscar_semantica(a)", "leer_cv(b)"]) == []
