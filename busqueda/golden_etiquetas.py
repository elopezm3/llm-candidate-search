"""Golden Dataset labels (2026-11-17): reviewed against all 97 CV profiles, not only the proposals.
Labelled by Claude at the user's request; the cases in REVISAR are the ones a human should double-check.

    python3 -m busqueda.golden_etiquetas   # writes data/golden/golden_dataset.json (0 API calls)
"""
import json

from data_extraction.rutas import CVS, GOLDEN, SALIDA_VACANTES

# vacante number (sorted file order, same as V01..V30 in DECISIONS.md) -> (expected CV name stems, difficulty, reason)
VACANTES = {
    1: (["cv-49", "cv-86", "cv-15"], "dificil",
        "Agents and automation with n8n/CrewAI/LangChain; three different profiles fit."),
    2: (["cv-27", "cv-15", "cv-66", "cv-73"], "dificil",
        "4+ years building with LLMs in production; four AI engineers of different seniority."),
    3: (["cv-09", "cv-26", "cv-86"], "dificil",
        "Process transformation: BPM/BPMN consulting and digital transformation leads."),
    4: (["cv-46"], "facil", "Mobile bank sales: the only business-admin profile with a commercial lead role."),
    6: (["cv-59", "cv-35"], "dificil",
        "Junior business analyst with Power BI; business admin vs. business analyst."),
    7: (["cv-21", "cv-59"], "dificil", "Power BI + Power Apps + Power Automate for customer service tooling."),
    9: (["cv-12", "cv-87", "cv-51", "cv-35"], "dificil",
        "Junior analytics with Python and SQL; four early-career data profiles."),
    10: (["cv-26", "cv-40"], "dificil", "Senior IT architecture (UML), systems engineering."),
    11: (["cv-02", "cv-97"], "dificil", "BTL marketing and brand activations: brand manager and marketing director."),
    12: (["cv-40", "cv-86"], "dificil",
         "Coordinating software development services: software engineering lead and product manager."),
    13: (["cv-15", "cv-66", "cv-27"], "dificil",
         "Organisation-wide AI strategy: senior AI leads with consulting/product experience."),
    14: (["cv-42", "cv-79", "cv-77"], "dificil",
         "Commercial director with an engineering background plus MBA/marketing. (cv-42 and cv-79 are the same CV, an anonymisation duplicate.)"),
    15: (["cv-08", "cv-25"], "dificil", "Engineering project director with 6+ years."),
    16: (["cv-46", "cv-44"], "dificil", "Payroll agreements: business admin with commercial or credit experience."),
    18: (["cv-49", "cv-17", "cv-73"], "dificil",
         "Chatbots/agents with Python and LangChain, 2+ years."),
    20: (["cv-78"], "facil", ".NET/C#/Azure developer: the only one with that stack."),
    21: (["cv-78", "cv-32"], "dificil", "Full stack React + .NET/Node + Azure, 4+ years."),
    24: (["cv-69", "cv-81", "cv-87", "cv-63"], "dificil",
         "Junior software engineer programme: early-career systems/software profiles."),
    26: (["cv-58", "cv-41", "cv-91"], "dificil", "Quantitative market research: economics and market intelligence."),
    27: (["cv-27", "cv-15", "cv-11"], "dificil", "Leading AI teams with cloud ML, 5+ years."),
    28: (["cv-49", "cv-86"], "dificil", "AI automations with n8n/Make and LLMs for business teams."),
    29: (["cv-38", "cv-85", "cv-04"], "dificil",
         "Strategic projects for economic development: acceleration programmes, tech transfer, project management."),
    30: (["cv-11", "cv-73"], "dificil", "Spark + Airflow + AWS data engineering, 4+ years."),
}
OMITIDAS = {5: "Near-duplicate of V03 (same bank, same role family).", 8: "SAP BW/HANA specialist: nobody has SAP data experience.",
            17: "Insurance analyst: nobody has insurance experience.", 19: "Requires a law degree; the only lawyer is corporate, not research management.",
            22: "IBM MQ middleware: nobody has it.", 23: "QA automation (Playwright/Karate): there are no testers.", 25: "IBM ACE/MQ middleware: nobody has it."}
# Easy free-text queries, like the course's own example (one obvious candidate each).
CONSULTAS = [
    ("Enfermera profesional con experiencia en unidad de cuidados intensivos", ["cv-01"]),
    ("Chef ejecutivo con experiencia en cocina caribeña", ["cv-76"]),
    ("Abogado corporativo especializado en derecho comercial internacional y contratos", ["cv-68"]),
    ("Director de arte y diseñador gráfico con Illustrator y Photoshop", ["cv-88"]),
    ("Geólogo de minas con experiencia en minería subterránea", ["cv-10"]),
]
REVISAR = [4, 11, 12, 16, 29]  # least certain: a human recruiter should confirm these


def archivo(stem: str) -> str:
    hits = [p.name for p in CVS.iterdir() if p.stem in (stem, f"{stem}_CV")]
    assert len(hits) == 1, (stem, hits)
    return hits[0]


if __name__ == "__main__":
    vacantes = sorted(SALIDA_VACANTES.glob("*.vac-v2.json"))
    casos = []
    for n, (stems, dificultad, razon) in VACANTES.items():
        r = json.loads(vacantes[n - 1].read_text())
        casos.append({"id": f"V{n:02d}", "tipo": "vacante", "vacante_archivo": r["source_file"], "cargo": r["vacante"]["cargo"],
                      "esperados": [archivo(s) for s in stems], "dificultad": dificultad, "razon": razon, "revisar": n in REVISAR})
    for i, (consulta, stems) in enumerate(CONSULTAS, 1):
        casos.append({"id": f"Q{i:02d}", "tipo": "consulta", "consulta": consulta, "esperados": [archivo(s) for s in stems],
                      "dificultad": "facil", "razon": "One obvious candidate (sanity check).", "revisar": False})
    GOLDEN.mkdir(parents=True, exist_ok=True)
    (GOLDEN / "golden_dataset.json").write_text(json.dumps(casos, ensure_ascii=False, indent=2))
    (GOLDEN / "vacantes_omitidas.json").write_text(json.dumps({f"V{n:02d}": m for n, m in OMITIDAS.items()}, ensure_ascii=False, indent=2))
    dif = sum(c["dificultad"] == "dificil" for c in casos)
    print(f"{len(casos)} cases ({len(VACANTES)} postings + {len(CONSULTAS)} queries): {dif} hard, {len(casos) - dif} easy · "
          f"{sum(len(c['esperados']) for c in casos)} expected CVs · {len(OMITIDAS)} postings omitted · to double-check: {['V%02d' % n for n in REVISAR]}")
