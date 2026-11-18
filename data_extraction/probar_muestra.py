"""Run the 5-CV sample with the current schema (text+image), cached per schema version.
The free tier allows 20 requests/day, so schema iterations only run here, never on all 97 CVs.
`python3 -m data_extraction.probar_muestra texto vision ambos` re-runs the step 2b comparison."""
import atexit
import json
import sys
from pathlib import Path

from .extraer_cvs import SCHEMA_VERSION, LimiteAlcanzado, extraer, registrar_costo, reporte_uso
from .rutas import CVS, MUESTRAS, SALIDA_MUESTRA as SALIDA

MUESTRA = [
    CVS / "cv-52",              # two columns, labels split from values
    CVS / "cv-16",   # form layout, durations instead of dates
    CVS / "cv-15",           # English, many technologies
    CVS / "cv-65",                  # Word, content in content controls (w:sdt)
    MUESTRAS / "cv-02.md",       # Markdown (pandoc conversion of her .docx)
]
SALIDA.mkdir(parents=True, exist_ok=True)


def obtener(path: Path, metodo: str) -> dict:
    """Disk cache: an existing JSON is reused instead of calling the API again."""
    archivo = SALIDA / f"{path.stem}.{SCHEMA_VERSION}.{metodo}.json"
    if not archivo.exists():
        print(f"  calling Gemini: {path.name} · {metodo}")
        forzar = None if metodo == "ambos" else metodo
        archivo.write_text(json.dumps(extraer(path, forzar=forzar), ensure_ascii=False, indent=2))
    return json.loads(archivo.read_text())


def resumen(r: dict) -> dict:
    cv = r["cv"]
    return {
        "nombre": cv["nombre_completo"],
        "emails": cv["emails"],
        "telefonos": cv["telefonos"],
        "ciudad": f"{cv['ciudad']}, {cv['pais']}",
        "experiencias": len(cv["experiencia"]),
        "educacion": len(cv["educacion"]),
        "tecnologias": len(cv["tecnologias"]),
        "idiomas": [f"{i['idioma']} {i.get('nivel') or ''}".strip() for i in cv["idiomas"]],
        "anos_exp": r["anos_experiencia"],
        "sospechoso": len(cv["texto_sospechoso"]),
        "tokens": f"{r['uso']['entrada']}+{r['uso']['salida']} (${r['uso']['costo_usd']})" if "uso" in r else f"{r['tokens']['entrada']}+{r['tokens']['salida']}",
    }


if __name__ == "__main__":
    atexit.register(registrar_costo, "Sample (5 CVs)")
    metodos = sys.argv[1:] or ["ambos"]
    for path in MUESTRA:
        print(f"\n=== {path.name}")
        try:
            resultados = {m: resumen(obtener(path, m)) for m in metodos}
        except Exception as e:
            if isinstance(e, LimiteAlcanzado) or "PerDay" in str(e):
                print(f"  {e}" if isinstance(e, LimiteAlcanzado) else "  Daily quota exhausted, stopping.")
                break
            print(f"  FAILED, skipping (re-run to retry only the missing ones): {type(e).__name__}: {str(e)[:200]}")
            continue
        for campo in resultados[metodos[0]]:
            valores = [resultados[m][campo] for m in metodos]
            if all(v == valores[0] for v in valores):
                print(f"  {campo:13} {valores[0]}")
            else:
                print(f"≠ {campo:13} " + f"\n{'':16}".join(f"{m}: {v}" for m, v in zip(metodos, valores)))
    print(f"\nThis run: {reporte_uso()}")
