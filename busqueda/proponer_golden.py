"""Proposes Golden Dataset candidates for each job posting from the Module 1 structured data, WITHOUT embeddings,
so the test set isn't biased toward the method being evaluated. The user validates every case by hand.

    python3 -m busqueda.proponer_golden    # writes data/golden/propuesta_golden.md (0 API calls)
"""
import json
import math
import re
import unicodedata

from data_extraction.rutas import GOLDEN, SALIDA_CVS, SALIDA_VACANTES

NIVELES = ["curso", "bachiller", "tecnico", "tecnologo", "pregrado", "especializacion", "maestria", "doctorado"]
VACIAS = set("""para como con los las del una uno por que sus son ser más mas este esta entre sobre desde hasta
también tambien otros otras cada todo toda todos todas donde cuando experiencia conocimiento conocimientos manejo
años anos nivel area areas trabajo equipo equipos empresa cargo the and with for from your will our you are who""".split())


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"^microsoft ", "", t.strip())


def _palabras(*textos: str) -> set[str]:
    return {w for t in textos for w in re.findall(r"[a-z]{5,}", _norm(t)) if w not in VACIAS}


def perfil_cv(r: dict) -> dict:
    cv = r["cv"]
    return {
        "archivo": r["source_file"],
        "tech": {_norm(t) for t in cv["tecnologias"]},
        "palabras": _palabras(*(e["cargo"] for e in cv["experiencia"]), *(e["titulo"] for e in cv["educacion"]),
                              cv["perfil_literal"] or ""),
        "anos": r["anos_experiencia"],
        "nivel": max((NIVELES.index(e["nivel"]) for e in cv["educacion"]), default=-1),
        "ultimo_cargo": cv["experiencia"][0]["cargo"] if cv["experiencia"] else "-",
        "titulo": max(cv["educacion"], key=lambda e: NIVELES.index(e["nivel"]))["titulo"] if cv["educacion"] else "-",
    }


def puntaje(v: dict, c: dict, idf: dict[str, float]) -> tuple[float, list[str], list[str]]:
    """Technologies weigh most; shared words are weighted by rarity (IDF), so 'datos' or 'desarrollo' barely count."""
    req, des = {_norm(t) for t in v["tecnologias_requeridas"]}, {_norm(t) for t in v["tecnologias_deseables"]}
    tech = sorted((req | des) & c["tech"])
    pal = sorted(_palabras(v["cargo"], *v["areas_formacion"]) & c["palabras"])  # responsibilities add generic noise
    p = 3 * len(req & c["tech"]) + 1.5 * len(des & c["tech"]) + sum(idf[w] for w in pal)
    pal = sorted(pal, key=lambda w: -idf[w])
    if v["anos_experiencia_min"] and c["anos"] is not None:
        p += 1 if c["anos"] >= v["anos_experiencia_min"] else -2
    if v["nivel_educativo_min"]:
        p += 1 if c["nivel"] >= NIVELES.index(v["nivel_educativo_min"]) else -1
    return p, tech, pal


if __name__ == "__main__":
    cvs = [perfil_cv(json.loads(f.read_text())) for f in sorted(SALIDA_CVS.glob("*.cv-v8.json")) if not f.name.startswith("_")]
    vacantes = [json.loads(f.read_text()) for f in sorted(SALIDA_VACANTES.glob("*.vac-v2.json"))]
    df = {}
    for c in cvs:
        for w in c["palabras"]:
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log(len(cvs) / n) for w, n in df.items()}
    out = ["# Golden Dataset: propuesta para validar",
           "",
           "Para cada vacante: marca con `[x]` las hojas de vida que **un reclutador de verdad consideraría correctas**.",
           "Puedes marcar 1, varias o ninguna. Si conoces otra que no aparece, escribe su archivo en la línea `Otros:`.",
           "Si una vacante no tiene ningún candidato razonable, déjala sin marcar y quedará fuera del dataset.",
           "Las propuestas salen de cruzar los datos estructurados del Módulo 1 (no de embeddings), así que pueden equivocarse: tu criterio manda.",
           ""]
    for r in vacantes:
        v = r["vacante"]
        ranking = sorted(((puntaje(v, c, idf), c) for c in cvs), key=lambda x: -x[0][0])[:5]
        out += [f"## {v['cargo']}",
                f"`{r['source_file']}`  ",
                f"Pide: exp ≥ {v['anos_experiencia_min'] or '—'} años · {v['nivel_educativo_min'] or '—'} · "
                f"{', '.join(v['areas_formacion'][:3]) or '—'} · tech: {', '.join(v['tecnologias_requeridas'][:6]) or '—'}",
                ""]
        for (p, tech, pal), c in ranking:
            out.append(f"- [ ] `{c['archivo']}`: {c['ultimo_cargo'][:60]} · {c['anos'] if c['anos'] is not None else '?'} años · "
                       f"{c['titulo'][:50]} · coincide: {', '.join(tech[:4] + pal[:5]) or '—'} (puntaje {p:.1f})")
        out += ["", "Otros: ", ""]
    (GOLDEN / "propuesta_golden.md").write_text("\n".join(out))
    print(f"{len(vacantes)} vacantes × 5 candidatos → data/golden/propuesta_golden.md")
