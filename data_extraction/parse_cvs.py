"""Step 2: parse every CV locally (no LLM) and decide text vs vision per page."""
import re
import sys
from pathlib import Path

import docx
import pymupdf
from docx.oxml.ns import qn

from .rutas import CVS


def necesita_vision(texto: str, cobertura_imagen: float) -> str | None:
    """Per page: returns the reason to use vision, or None if the text is usable."""
    # ponytail: thresholds calibrated on these 97 CVs, revisit when new sources arrive
    visibles = "".join(texto.split())
    n = len(visibles)
    if n < 50:
        return "sin_texto" if cobertura_imagen > 0.05 else "vacia"
    if cobertura_imagen > 0.5:
        return "pagina_imagen"
    if texto.count("(cid:") + texto.count("�") > 20:
        return "codificacion_rota"
    if sum(c.isalpha() for c in visibles) / n < 0.5:
        return "texto_basura"
    return None


def _limpiar(texto: str) -> str:
    """Strip trailing spaces and collapse runs of blank lines (layout padding costs tokens)."""
    return re.sub(r"\n{3,}", "\n\n", "\n".join(l.rstrip() for l in texto.splitlines())).strip()


def _claro(color: int) -> bool:
    return min((color >> 16) & 255, (color >> 8) & 255, color & 255) > 240


def textos_ocultos(page: pymupdf.Page, imagenes: list[pymupdf.Rect]) -> list[str]:
    """Spans a human can't see: light text on a light background, tiny fonts, or off-page."""
    fondos_oscuros = imagenes + [
        d["rect"] for d in page.get_drawings() if d.get("fill") and min(d["fill"]) < 0.9
    ]
    ocultos = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                if not s["text"].strip():
                    continue
                caja = pymupdf.Rect(s["bbox"])
                invisible = _claro(s["color"]) and not any(f.contains(caja) for f in fondos_oscuros)
                if invisible or s["size"] < 2 or not page.rect.intersects(caja):
                    ocultos.append(s["text"].strip())
    return ocultos


def parse_pdf(path: Path) -> list[dict]:
    paginas = []
    with pymupdf.open(path) as doc:
        for page in doc:
            bloques = page.get_text("dict")["blocks"]
            imagenes = [pymupdf.Rect(b["bbox"]) for b in bloques if b["type"] == 1]
            cobertura = min(sum(r.get_area() for r in imagenes) / page.rect.get_area(), 1.0)
            texto = _limpiar(page.get_text())
            paginas.append({
                "texto": texto,
                "cobertura_imagen": cobertura,
                "motivo": necesita_vision(texto, cobertura),
                "texto_oculto": textos_ocultos(page, imagenes),
            })
    return paginas


def parse_docx(path: Path) -> list[dict]:
    # Walk every paragraph in document order: body, tables and content controls (w:sdt),
    # which Document.paragraphs skips. A run belongs to its nearest paragraph, so text boxes aren't duplicated.
    body = docx.Document(path).element.body
    lineas = [
        "".join(t.text or "" for t in p.iter(qn("w:t")) if next(t.iterancestors(qn("w:p"))) is p)
        for p in body.iter(qn("w:p"))
    ]
    return [{"texto": _limpiar("\n".join(lineas)), "cobertura_imagen": 0.0, "motivo": None, "texto_oculto": []}]


def parse(path: Path) -> list[dict]:
    if path.suffix == ".md":
        paginas = [{"texto": _limpiar(path.read_text()), "cobertura_imagen": 0.0, "motivo": None, "texto_oculto": []}]
    elif path.suffix == ".pdf":
        paginas = parse_pdf(path)
    elif path.suffix == ".docx":
        paginas = parse_docx(path)
    else:
        raise ValueError(f"Unsupported file type '{path.suffix}' (expected .pdf, .docx or .md): {path.name}")
    for p in paginas:
        p["metodo"] = {None: "texto", "vacia": "omitir"}.get(p["motivo"], "vision")
    return paginas


if __name__ == "__main__":
    assert necesita_vision("", 0) == "vacia"
    assert necesita_vision("", 0.9) == "sin_texto"
    assert necesita_vision("D  a  t  o  s \n \n \n \n \n \n \n \n" * 20, 0) is None
    assert necesita_vision("Hola mundo " * 50, 0.9) == "pagina_imagen"
    assert necesita_vision("(cid:72)" * 30 + "a" * 300, 0) == "codificacion_rota"
    assert necesita_vision("1234 ---- " * 50, 0) == "texto_basura"
    assert necesita_vision("Estudios Primarios: Escuela Rural 1973", 0) == "vacia"
    assert necesita_vision("Estudios Primarios: Escuela Rural, Sector 3, Vereda Centro 1973 / 1977", 0.2) is None

    if len(sys.argv) > 1:  # print one CV: python3 -m data_extraction.parse_cvs <file name>
        for i, p in enumerate(parse(CVS / sys.argv[1]), 1):
            print(f"--- página {i} · {p['metodo']} {p['motivo'] or ''} · ocultos: {p['texto_oculto']}\n{p['texto']}")
        sys.exit()

    print(f"{'archivo':45} {'pag':>3} {'chars':>6} {'vision':>14} oculto")
    for path in sorted(CVS.iterdir()):
        if path.suffix not in (".pdf", ".docx", ".md"):
            continue
        paginas = parse(path)
        vision = [i for i, p in enumerate(paginas, 1) if p["metodo"] == "vision"]
        ocultos = [t for p in paginas for t in p["texto_oculto"]]
        print(
            f"{path.name[:45]:45} {len(paginas):>3} {sum(len(p['texto'].strip()) for p in paginas):>6} "
            f"{str(vision) if vision else '-':>14} {ocultos[:4] if ocultos else '-'}"
        )
