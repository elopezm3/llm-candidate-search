"""Every folder path of the project, in one place."""
from pathlib import Path

PROYECTO = Path(__file__).resolve().parents[1]
CVS = PROYECTO / "data" / "raw" / "CVs"
MUESTRAS = PROYECTO / "data" / "samples"
SALIDA_CVS = PROYECTO / "data" / "processed" / "cvs"
SALIDA_MUESTRA = PROYECTO / "data" / "processed" / "muestra"
COSTOS = PROYECTO / "COSTOS.md"
RESALTADOS = PROYECTO / "data" / "processed" / "resaltados"
VACANTES = PROYECTO / "data" / "raw" / "Vacantes"
SALIDA_VACANTES = PROYECTO / "data" / "processed" / "vacantes"
GOLDEN = PROYECTO / "data" / "golden"
