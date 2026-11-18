"""Highlights in the PDF where each extracted value came from (course lesson 29), so a recruiter can verify it at a glance.
Pure local work: reads saved results, never calls the API. Only PDFs (Word/Markdown have no pages to highlight).

    python3 -m data_extraction.resaltar            # full-run results (data/processed/cvs)
    python3 -m data_extraction.resaltar muestra    # sample results (data/processed/muestra)

Colours: experiencia yellow · educacion green · idiomas blue · ubicación pink. Clicking a highlight shows its field.
Copies go to data/processed/resaltados/; the original PDFs are never modified.
"""
import json
import sys

import pymupdf

from .extraer_cvs import OMITIR, SCHEMA_VERSION, _normalizar, trozos_cita
from .rutas import CVS, MUESTRAS, RESALTADOS, SALIDA_CVS, SALIDA_MUESTRA

COLORES = {"experiencia": (1, 0.9, 0.2), "educacion": (0.5, 0.9, 0.5), "idiomas": (0.5, 0.8, 1), "cita_ubicacion": (1, 0.6, 0.8)}


def _tokens(page: pymupdf.Page) -> list[tuple[str, pymupdf.Rect]]:
    """Every normalized token on the page with the rect of the word it came from ('(I.T.M.)' gives 3 tokens)."""
    return [(t, pymupdf.Rect(w[:4])) for w in page.get_text("words") for t in _normalizar(w[4]).split()]


def _buscar(trozo: str, tokens: list[tuple[str, pymupdf.Rect]]) -> list[pymupdf.Rect] | None:
    objetivo = trozo.split()
    for k in range(len(tokens) - len(objetivo) + 1):
        if all(tokens[k + n][0] == t for n, t in enumerate(objetivo)):
            return [r for _, r in tokens[k:k + len(objetivo)]]
    return None


def resaltar(resultado: dict) -> tuple[int, int]:
    """Writes the highlighted copy; returns (quotes highlighted, quotes total)."""
    cv, nombre = resultado["cv"], resultado["source_file"]
    origen = CVS / nombre if (CVS / nombre).exists() else MUESTRAS / nombre
    citas = [(f"experiencia[{i}]", e["cita"]) for i, e in enumerate(cv["experiencia"])]
    citas += [(f"educacion[{i}]", e["cita"]) for i, e in enumerate(cv["educacion"])]
    citas += [(f"idiomas[{i}]", e["cita"]) for i, e in enumerate(cv["idiomas"])]
    citas += [("cita_ubicacion", cv["cita_ubicacion"])] if cv.get("cita_ubicacion") else []
    hechas = 0
    with pymupdf.open(origen) as doc:
        paginas = [p for p in doc if p.number not in OMITIR.get(nombre, ())]
        tokens = {p.number: _tokens(p) for p in paginas}
        texto = _normalizar("\n".join(p.get_text() for p in paginas))
        for campo, cita in citas:
            trozos = trozos_cita(cita, texto) or []
            encontrados = 0
            for trozo in trozos:
                for p in paginas:
                    if rects := _buscar(trozo, tokens[p.number]):
                        a = p.add_highlight_annot(rects)
                        a.set_colors(stroke=COLORES[campo.split("[")[0]])
                        a.set_info(title=campo, content=cita)
                        a.update()
                        encontrados += 1
                        break
            hechas += bool(trozos) and encontrados == len(trozos)
        RESALTADOS.mkdir(parents=True, exist_ok=True)
        doc.save(RESALTADOS / f"{origen.stem}_resaltado.pdf")
    return hechas, len(citas)


if __name__ == "__main__":
    carpeta = SALIDA_MUESTRA if sys.argv[1:] == ["muestra"] else SALIDA_CVS
    for f in sorted(carpeta.glob(f"*.{SCHEMA_VERSION}*.json")):
        if f.name.startswith("_"):
            continue
        r = json.loads(f.read_text())
        if not r["source_file"].endswith(".pdf"):
            continue
        hechas, total = resaltar(r)
        print(f"{r['source_file']:45} {hechas}/{total} quotes highlighted → resaltados/{f.name.split('.')[0]}_resaltado.pdf")
