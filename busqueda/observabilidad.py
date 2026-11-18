"""Module 7: Langfuse client (self-hosted at http://localhost:3000) with personal-data masking applied BEFORE anything
leaves the process (lesson 24, Ley 1581). Imported by every traced module, so no code path can create an unmasked client.

What is masked (regex, Colombian formats): e-mails → [CORREO], mobiles (3xx, optional +57) → [CELULAR],
landlines ((60x) xxx xxxx) → [TELEFONO], ID numbers only when preceded by "C.C." / "cédula" → [DOCUMENTO].
Names are NOT masked: regex can't do it reliably (needs NER) and recruiters need them; a written product decision.

Tests set LANGFUSE_TEST_EXPORT=1: same client, same mask, but spans go to an in-memory exporter (lesson 25).
"""
import os
import re

from dotenv import load_dotenv
from langfuse import Langfuse

load_dotenv()

_PATRONES = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[CORREO]"),
    (re.compile(r"(?:C\.?\s?C\.?|c[ée]dula(?:\s+de\s+ciudadan[ií]a)?)[\s:#No.]*\d[\d.\s]{5,13}\d", re.IGNORECASE), "[DOCUMENTO]"),
    (re.compile(r"(?<!\d)(?:\+?57[\s-]?)?3\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"), "[CELULAR]"),
    (re.compile(r"\(?60\d\)?[\s-]?\d{3}[\s-]?\d{4}(?!\d)"), "[TELEFONO]"),
]


def mascara(*, data, **kwargs):
    """Langfuse calls this on every input/output/metadata; walks dicts and lists down to strings."""
    if isinstance(data, str):
        for patron, reemplazo in _PATRONES:
            data = patron.sub(reemplazo, data)
        return data
    if isinstance(data, dict):
        return {k: mascara(data=v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [mascara(data=v) for v in data]
    return data


EXPORTADOR = None
if os.environ.get("LANGFUSE_TEST_EXPORT") == "1":
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    EXPORTADOR = InMemorySpanExporter()

langfuse = Langfuse(mask=mascara, **({"span_exporter": EXPORTADOR, "base_url": "http://localhost:9"} if EXPORTADOR else {}))


if __name__ == "__main__":
    muestra = {"q": "Escribir a ana.perez@correo.co o al +57 300 111 22 33, fijo (601) 555 0000, C.C. 62.256.134",
               "lista": ["300 777 8899", "año 2023-2024", "12 años"]}
    print(mascara(data=muestra))
    assert mascara(data="ana@x.co") == "[CORREO]"
    assert mascara(data="Cel: 300 111 22 33") == "Cel: [CELULAR]"
    assert mascara(data="(601) 555 0000") == "[TELEFONO]"
    assert mascara(data="C.C. 62.256.134") == "[DOCUMENTO]"
    assert mascara(data="Trabajó 2015-2023, 8 años, 1.200 contactos") == "Trabajó 2015-2023, 8 años, 1.200 contactos"  # no false positives
    print("mask ok")
