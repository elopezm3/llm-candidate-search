"""Module 3: two chunking strategies for the CVs (no API calls).

- recursivo: ~500 tokens, 10% overlap, cutting at the biggest natural separator that fits (paragraph → line → sentence → word).
- secciones: split at CV section headings (experience, education, skills, profile...), Spanish and English; sections longer
  than the limit fall back to the recursive splitter, and every sub-chunk carries its section title (lesson 12).
Both merge chunks under ~30 tokens into the next one (lesson 19: a bare title wins the search and answers nothing).

    python3 -m busqueda.chunking     # chunk statistics + a sample CV (0 API calls)
"""
import re
import unicodedata
from statistics import median

TOKENS_POR_CHAR = 0.25  # ponytail: chars/4 estimate; use the model's tokenizer if exact counts ever matter
MAX_CHARS = 2000        # ≈ 500 tokens
SOLAPE_CHARS = 200      # ≈ 10% overlap
MIN_CHARS = 120         # ≈ 30 tokens
SEPARADORES = ["\n\n", "\n", ". ", " "]

TITULOS = re.compile(r"^\W*(experiencia|experience|trayectoria|historia laboral|formacion|educacion|education|estudios|"
                     r"academic|habilidades|skills|competencias|conocimientos|aptitudes|perfil|profile|resumen|summary|"
                     r"acerca de|about|idiomas|languages|certificaciones|certifications|certificados|cursos|courses|"
                     r"proyectos|projects|referencias|references|logros|achievements|publicaciones|publications|"
                     r"investigacion|research|datos personales|informacion personal|contacto|contact|voluntariado|"
                     r"volunteer|premios|awards|herramientas|tools|tecnologias|technologies)\b", re.IGNORECASE)


def tokens(texto: str) -> int:
    return round(len(texto) * TOKENS_POR_CHAR)


def _sin_tildes(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def _partir(texto: str, max_chars: int, seps: list[str]) -> list[str]:
    """Pieces no longer than max_chars, cutting at the biggest separator that works."""
    if len(texto) <= max_chars or not seps:
        return [texto]
    sep, resto = seps[0], seps[1:]
    piezas, actual = [], ""
    for parte in texto.split(sep):
        candidato = f"{actual}{sep}{parte}" if actual else parte
        if len(candidato) <= max_chars:
            actual = candidato
            continue
        if actual:
            piezas.append(actual)
        if len(parte) > max_chars:
            piezas += _partir(parte, max_chars, resto)
            actual = ""
        else:
            actual = parte
    return piezas + ([actual] if actual else [])


def _fusionar_pequenos(chunks: list[str]) -> list[str]:
    """Chunks under MIN_CHARS join the next one; a small leftover at the end joins the previous one."""
    out, pendiente = [], ""
    for c in chunks:
        c = (pendiente + "\n" + c).strip() if pendiente else c
        if len(c) < MIN_CHARS:
            pendiente = c
        else:
            out.append(c)
            pendiente = ""
    if pendiente:
        if out:
            out[-1] += "\n" + pendiente
        else:
            out.append(pendiente)
    return out


def recursivo(texto: str) -> list[dict]:
    piezas = [p.strip() for p in _partir(texto.strip(), MAX_CHARS - SOLAPE_CHARS, SEPARADORES) if p.strip()]
    chunks = []
    for i, p in enumerate(piezas):
        cola = piezas[i - 1][-SOLAPE_CHARS:].split(" ", 1)[-1] if i else ""  # overlap starts at a word boundary
        chunks.append((cola + " " + p).strip() if cola else p)
    return [{"seccion": None, "texto": t} for t in _fusionar_pequenos(chunks)]


def secciones(texto: str) -> list[dict]:
    bloques, titulo, actual = [], "Encabezado", []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if limpia and len(limpia) <= 50 and TITULOS.match(_sin_tildes(limpia)):
            if "\n".join(actual).strip():
                bloques.append((titulo, "\n".join(actual).strip()))
            titulo, actual = limpia.strip(":").strip(), []
        else:
            actual.append(linea)
    if "\n".join(actual).strip():
        bloques.append((titulo, "\n".join(actual).strip()))
    out = []
    for titulo, cuerpo in bloques:
        for pieza in _fusionar_pequenos([p.strip() for p in _partir(cuerpo, MAX_CHARS, SEPARADORES) if p.strip()]):
            out.append({"seccion": titulo, "texto": f"{titulo}\n{pieza}"})  # title inside the embedded text (lesson 12)
    # A whole section can be tiny ("IDIOMAS: Inglés básico"): merge it into the next section, keeping both titles.
    fusion, pendiente = [], None
    for c in out:
        if pendiente:
            c = {"seccion": f"{pendiente['seccion']} + {c['seccion']}", "texto": pendiente["texto"] + "\n\n" + c["texto"]}
            pendiente = None
        if len(c["texto"]) < MIN_CHARS:
            pendiente = c
        else:
            fusion.append(c)
    if pendiente:
        if fusion:
            fusion[-1] = {"seccion": f"{fusion[-1]['seccion']} + {pendiente['seccion']}", "texto": fusion[-1]["texto"] + "\n\n" + pendiente["texto"]}
        else:
            fusion.append(pendiente)
    return fusion


ESTRATEGIAS = {"recursivo": recursivo, "secciones": secciones}


if __name__ == "__main__":
    from .consultas import corpus
    docs = corpus()
    for nombre, f in ESTRATEGIAS.items():
        por_cv = {a: f(t) for a, t in docs.items()}
        tam = sorted(tokens(c["texto"]) for cs in por_cv.values() for c in cs)
        print(f"{nombre:10} {sum(map(len, por_cv.values())):5} chunks · tokens min {tam[0]} / median {median(tam):.0f} / max {tam[-1]} · "
              f"total ≈ {sum(tam):,} tokens · chunks/CV median {median(len(c) for c in por_cv.values()):.0f}")
        if nombre == "secciones":
            sin = [a for a, cs in por_cv.items() if all(c["seccion"] == "Encabezado" for c in cs)]
            print(f"           CVs with no heading detected: {len(sin)} {[s[:28] for s in sin[:6]]}")
    print("\nSample, cv-86 (sections):")
    for c in secciones(docs["cv-86"]):
        print(f"  [{c['seccion'][:30]:30}] {tokens(c['texto']):4} tok · {c['texto'][len(c['seccion']) + 1:][:90]!r}")
