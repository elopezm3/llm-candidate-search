"""Full run: every CV in data/raw/CVs -> data/processed/cvs/<name>.<schema_version>.json. Run from project/.

    python3 -m data_extraction.extraer_todos                                # dry run: CVs pending + cost estimate, 0 requests
    LIMITE_REQUESTS=150 python3 -m data_extraction.extraer_todos --correr   # real run, stops after 150 requests

Already-extracted CVs (same schema version) are skipped, so an interrupted run resumes where it stopped.
One CV failing doesn't stop the run; a daily-quota error does, since every following request would fail too."""
import atexit
import json
import sys
import traceback
from pathlib import Path

from .extraer_cvs import LIMITE_REQUESTS, SCHEMA_VERSION, LimiteAlcanzado, extraer, registrar_costo, reporte_uso
from .rutas import CVS, SALIDA_CVS as SALIDA, SALIDA_MUESTRA as MUESTRA
from .revision import imprimir, revisar
from .resaltar import resaltar



def costo_medido() -> list[float]:
    """Measured cost per CV (retries included) from sample runs with the current schema."""
    return [json.loads(f.read_text())["uso"]["costo_usd"] for f in MUESTRA.glob(f"*.{SCHEMA_VERSION}.ambos.json")]


def pendientes() -> list[Path]:
    cvs = sorted(p for p in CVS.iterdir() if p.suffix in (".pdf", ".docx", ".md"))
    return [p for p in cvs if not (SALIDA / f"{p.stem}.{SCHEMA_VERSION}.json").exists()]


if __name__ == "__main__":
    atexit.register(registrar_costo, "Full run (all CVs)")
    SALIDA.mkdir(parents=True, exist_ok=True)
    todo = pendientes()
    print(f"schema {SCHEMA_VERSION}: {len(todo)} CVs pending → at least {len(todo)} requests (more if validation retries)")
    if costos := costo_medido():
        prom = sum(costos) / len(costos)
        print(f"measured on {len(costos)} sample CVs: avg ${prom:.4f}/CV, max ${max(costos):.4f} → "
              f"estimate ${prom * len(todo):.2f} (if every CV cost like the max: ${max(costos) * len(todo):.2f})")
    else:
        print("no sample measurement for this schema yet: run python3 -m data_extraction.probar_muestra first")
    print(f"request limit this run: {LIMITE_REQUESTS} (set LIMITE_REQUESTS to change)")
    if "--correr" not in sys.argv:
        print("Dry run. Add --correr to extract.")
        sys.exit()

    errores = []
    for n, path in enumerate(todo, 1):
        print(f"[{n}/{len(todo)}] {path.name}", flush=True)
        try:
            resultado = extraer(path)
        except LimiteAlcanzado as e:
            print(e)
            break
        except Exception as e:
            if "PerDay" in str(e):
                print("Daily quota exhausted, stopping. Re-run later; finished CVs are kept.")
                break
            errores.append({"source_file": path.name, "error": f"{type(e).__name__}: {e}"[:2000]})
            traceback.print_exc(limit=1)
            continue
        (SALIDA / f"{path.stem}.{SCHEMA_VERSION}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2))
        print(f"   ${resultado['uso']['costo_usd']:.4f} · total so far: {reporte_uso()}", flush=True)

    if errores:
        (SALIDA / f"_errores.{SCHEMA_VERSION}.json").write_text(json.dumps(errores, ensure_ascii=False, indent=2))
        print(f"{len(errores)} CVs failed, see data/processed/cvs/_errores.{SCHEMA_VERSION}.json")
    print(f"\nThis run: {reporte_uso()}")
    for f in sorted(SALIDA.glob(f"*.{SCHEMA_VERSION}.json")):
        if (r := json.loads(f.read_text()))["source_file"].endswith(".pdf"):
            resaltar(r)  # local only: highlighted copies in data/processed/resaltados/
    print("Highlighted PDFs: data/processed/resaltados/")
    imprimir(revisar(SALIDA), SALIDA)
