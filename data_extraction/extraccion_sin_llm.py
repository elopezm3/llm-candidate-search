"""Course exercise: extract the same 5 sample CVs WITHOUT an LLM and compare with Gemini's cached output.
Costs zero requests: it only reads the PDFs and the JSONs already in data/processed/muestra/."""
import json
import re
from pathlib import Path

from .extraer_cvs import Experiencia, anos_experiencia
from .parse_cvs import parse
from .probar_muestra import MUESTRA
from .rutas import SALIDA_MUESTRA as SALIDA

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TELEFONO = re.compile(r"(?:\(?\+?57\)?[\s.-]*)?(?:\(\d{3}\)\s?\d{3}\s?\d{4}|3\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2})")
MES = r"(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|jan|apr|aug|dec)[a-zé]*\.?"
RANGO = re.compile(
    rf"(?:({MES})\s+(?:de\s+)?)?(\d{{4}})\s*(?:[-–—]|\ba\b|to)\s*(?:({MES})\s+(?:de\s+)?)?(\d{{4}}|actual\w*|presente|present|current|hoy|la fecha)",
    re.IGNORECASE,
)
MESES = {m: i for i, m in enumerate(["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"], 1)}
MESES |= {"jan": 1, "apr": 4, "aug": 8, "dec": 12}
INICIO_EXP = re.compile(r"^\s*(experiencia|experience|trayectoria)", re.IGNORECASE)
FIN_EXP = re.compile(r"^\s*(formaci|educaci|education|estudios|referencias|references|habilidades|skills|idiomas|languages|publicaciones|cursos)", re.IGNORECASE)
IDIOMAS = {"Español": r"espa[nñ]ol|spanish", "Inglés": r"ingl[eé]s|english", "Francés": r"franc[eé]s|french",
           "Portugués": r"portugu[eé]s|portuguese", "Alemán": r"alem[aá]n|german", "Italiano": r"italian"}
# ponytail: a fixed keyword list only finds tools someone thought to add, which is exactly the limit this exercise shows
TECNOLOGIAS = ["Python", "SQL", "Excel", "Power BI", "Tableau", "R", "Java", "JavaScript", "TypeScript", "C#", "C++", "PHP",
               "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Git", "Linux", "PostgreSQL", "MySQL", "MongoDB", "Spark",
               "Pandas", "TensorFlow", "PyTorch", "LangChain", "OpenAI", "FastAPI", "Django", "React", "Node.js", "SAP",
               "Matlab", "AutoCAD", "Word", "PowerPoint", "Access", "n8n", "Airflow", "Snowflake", "Databricks"]


def _fecha(mes: str | None, año: str) -> str:
    return f"{año}-{MESES[mes[:3].lower()]:02d}" if mes and mes[:3].lower() in MESES else año


def seccion_experiencia(texto: str) -> str:
    """Lines between an 'Experiencia' heading and the next known heading. Whole text if no heading is found."""
    dentro, lineas = False, []
    for linea in texto.splitlines():
        if INICIO_EXP.match(linea) and len(linea) < 40:
            dentro = True
        elif FIN_EXP.match(linea) and len(linea) < 40:
            dentro = False
        elif dentro:
            lineas.append(linea)
    return "\n".join(lineas) or texto


def rangos(texto: str) -> list[Experiencia]:
    exps = []
    for m1, a1, m2, a2 in RANGO.findall(texto):
        actual = not a2.isdigit()
        exps.append(Experiencia(empresa="?", cargo="?", tipo="empleo", cita="", fecha_inicio=_fecha(m1, a1),
                                fecha_fin=None if actual else _fecha(m2, a2), actual=actual))
    return exps


def nombre(texto: str) -> str | None:
    """First short line of 2-5 capitalised words with no digits that isn't a document title."""
    for linea in texto.splitlines()[:25]:
        palabras = linea.split()
        if (2 <= len(palabras) <= 5 and not any(c.isdigit() for c in linea)
                and all(p[0].isupper() for p in palabras)
                and not re.search(r"hoja|vida|curr[ií]cul|resume|perfil|profile|datos", linea, re.IGNORECASE)):
            return linea.strip()
    return None


def extraer_sin_llm(path: Path) -> dict:
    texto = "\n".join(p["texto"] for p in parse(path) if p["metodo"] != "omitir")
    exps = rangos(seccion_experiencia(texto))
    return {
        "nombre": nombre(texto),
        "emails": sorted(set(EMAIL.findall(texto))),
        "telefonos": list(dict.fromkeys(TELEFONO.findall(texto))),
        "experiencias": len(exps),
        "anos_exp": anos_experiencia(exps),
        "idiomas": [i for i, patron in IDIOMAS.items() if re.search(patron, texto, re.IGNORECASE)],
        "tecnologias": [t for t in TECNOLOGIAS if re.search(rf"(?<![\w+#]){re.escape(t)}(?![\w+#])", texto)],
    }


def llm_guardado(path: Path) -> tuple[str, dict] | None:
    """Most recent cached Gemini output: newest schema version, preferring text+image > vision > text."""
    stem = path.stem
    candidatos = sorted((f for f in SALIDA.glob(f"{stem}.*.json") if f.name.split(".")[-2] in ("texto", "vision", "ambos")),
                        key=lambda f: (f.name.split(".")[-3], ["texto", "vision", "ambos"].index(f.name.split(".")[-2])))
    if not candidatos:
        return None
    f = candidatos[-1]
    return f.name.removeprefix(stem + "."), json.loads(f.read_text())


if __name__ == "__main__":
    assert EMAIL.findall("Correo: persona24@ejemplo.com.") == ["persona24@ejemplo.com"]
    assert TELEFONO.findall("Cel: 300 111 22 33 - (601) 555 0000 y +57 300 444 55 66") == ["300 111 22 33", "(601) 555 0000", "+57 300 444 55 66"]
    assert [(e.fecha_inicio, e.fecha_fin, e.actual) for e in rangos("Enero 2024 - Actualmente\n2004 – 2005\nJulio 2022 – diciembre 2023")] == \
        [("2024-01", None, True), ("2004", "2005", False), ("2022-07", "2023-12", False)]
    assert nombre("HOJA DE VIDA\ncv-91\n300 999 0000") == "cv-91"

    for path in MUESTRA:
        sin = extraer_sin_llm(path)
        guardado = llm_guardado(path)
        print(f"\n=== {path.name}   (LLM: {guardado[0] if guardado else 'no cached output'})")
        if not guardado:
            continue
        cv, r = guardado[1]["cv"], guardado[1]
        llm = {
            "nombre": cv["nombre_completo"], "emails": sorted(cv["emails"]), "telefonos": cv["telefonos"],
            "experiencias": len(cv["experiencia"]), "anos_exp": r["anos_experiencia"],
            "idiomas": [i["idioma"] for i in cv["idiomas"]], "tecnologias": cv["tecnologias"],
        }
        for campo in sin:
            a, b = sin[campo], llm[campo]
            if campo == "tecnologias":
                comun = {t.lower() for t in a} & {t.lower() for t in b}
                print(f"  tecnologias   sin LLM: {len(a)} · LLM: {len(b)} · in both: {len(comun)} · LLM only: {sorted(set(b) - {t for t in b if t.lower() in comun})[:8]}")
                continue
            igual = (sorted(map(str, a)) == sorted(map(str, b))) if isinstance(a, list) else a == b
            print(f"{'  ' if igual else '≠ '}{campo:13} sin LLM: {a}\n{'':15} LLM:     {b}" if not igual else f"  {campo:13} {a}")
