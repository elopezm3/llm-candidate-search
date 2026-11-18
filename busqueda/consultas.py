"""What gets embedded on each side of the search.

- Job posting → a SHORT query built from its extracted fields (course lesson 31: a posting isn't a query; retrieval models
  are trained on short-query ↔ long-document pairs, so embedding the whole posting compares document to document).
- CV → its full parsed text (Module 1 parser), skipping blank pages and the pages excluded in OMITIR.
"""
import json

from data_extraction.extraer_cvs import OMITIR
from data_extraction.parse_cvs import parse
from data_extraction.rutas import CVS, GOLDEN, SALIDA_VACANTES


def consulta_de_vacante(v: dict) -> str:
    partes = [v["cargo"].strip().rstrip(".") + "."]
    if v["anos_experiencia_min"]:
        partes.append(f"Mínimo {v['anos_experiencia_min']} años de experiencia.")
    if v["nivel_educativo_min"] or v["areas_formacion"]:
        partes.append(f"Formación: {v['nivel_educativo_min'] or ''} {'en ' + ', '.join(v['areas_formacion'][:3]) if v['areas_formacion'] else ''}".strip() + ".")
    tech = v["tecnologias_requeridas"][:8] + v["tecnologias_deseables"][:3]
    if tech:
        partes.append(f"Tecnologías: {', '.join(tech)}.")
    idiomas = [f"{i['idioma']} {i['nivel'] or ''}".strip() for i in v["idiomas"]]
    if idiomas:
        partes.append(f"Idiomas: {', '.join(idiomas)}.")
    return " ".join(partes)


def texto_cv(path) -> str:
    omitir = OMITIR.get(path.name, ())
    return "\n".join(p["texto"] for i, p in enumerate(parse(path)) if p["metodo"] != "omitir" and i not in omitir)


def casos() -> list[dict]:
    """Golden cases with the text to search for."""
    vacantes = {json.loads(f.read_text())["source_file"]: json.loads(f.read_text())["vacante"] for f in SALIDA_VACANTES.glob("*.vac-v2.json")}
    out = []
    for c in json.loads((GOLDEN / "golden_dataset.json").read_text()):
        c = dict(c)
        c["consulta"] = consulta_de_vacante(vacantes[c["vacante_archivo"]]) if c["tipo"] == "vacante" else c["consulta"]
        out.append(c)
    return out


def corpus() -> dict[str, str]:
    return {p.name: texto_cv(p) for p in sorted(CVS.iterdir()) if p.suffix in (".pdf", ".docx")}


if __name__ == "__main__":
    for c in casos()[:4] + casos()[-1:]:
        print(f"{c['id']}: {c['consulta']}")
    textos = corpus()
    print(f"\n{len(textos)} CVs, {sum(map(len, textos.values())):,} chars (≈ {sum(map(len, textos.values())) // 4:,} tokens)")
