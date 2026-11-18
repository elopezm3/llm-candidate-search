"""Manual-review list: CVs where Gemini flagged text that looks like instructions (possible prompt injection).
Nothing is discarded automatically; a recruiter decides (DECISIONS.md).

    python3 -m data_extraction.revision            # full-run outputs (data/processed/cvs)
    python3 -m data_extraction.revision muestra    # sample outputs (data/processed/muestra)
"""
import json
import sys
from pathlib import Path

from .extraer_cvs import SCHEMA_VERSION
from .rutas import SALIDA_CVS, SALIDA_MUESTRA


def revisar(carpeta: Path) -> list[dict]:
    pendientes = []
    for f in sorted(carpeta.glob(f"*.{SCHEMA_VERSION}*.json")):
        if f.name.startswith("_"):
            continue
        r = json.loads(f.read_text())
        if r["cv"]["texto_sospechoso"]:
            pendientes.append({
                "source_file": r["source_file"],
                "texto_sospechoso": r["cv"]["texto_sospechoso"],
                "texto_oculto": [o["texto"] for o in r["texto_oculto"]],  # context for the reviewer, not a flag by itself
            })
    (carpeta / f"_revision.{SCHEMA_VERSION}.json").write_text(json.dumps(pendientes, ensure_ascii=False, indent=2))
    return pendientes


def imprimir(pendientes: list[dict], carpeta: Path) -> None:
    print(f"\n{len(pendientes)} CVs need manual review (possible prompt injection) → {carpeta.name}/_revision.{SCHEMA_VERSION}.json")
    for p in pendientes:
        print(f"  • {p['source_file']}")
        for t in p["texto_sospechoso"]:
            print(f"      sospechoso: {t[:140]}")
        if p["texto_oculto"]:
            print(f"      hidden text in the file: {' '.join(p['texto_oculto'])[:140]}")


if __name__ == "__main__":
    carpeta = SALIDA_MUESTRA if sys.argv[1:] == ["muestra"] else SALIDA_CVS
    imprimir(revisar(carpeta), carpeta)
