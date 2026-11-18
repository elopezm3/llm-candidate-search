# LLM candidate search

An end-to-end AI system that extracts structured data from CVs and job postings and finds the best candidates for a role. It was built step by step, and every step was measured against a hand-reviewed golden dataset: extraction → semantic and hybrid search → RAG → workflow vs agent (LangGraph) → observability (Langfuse) → guardrails and memory.

Built as the course project of *AI Engineering: Fundamentos de Construcción de Aplicaciones de IA* (Majup Learn). The course provided the dataset: 97 anonymised CVs in Spanish/English and 30 job postings from Colombia (28 of them form the golden evaluation set). Every decision, number and dead end is logged in [`DECISIONS.md`](DECISIONS.md), and every API call's cost in [`COSTOS.md`](COSTOS.md). **Total API spend for the whole project: USD 3.29.**

## Results

| Stage | What was measured | Result |
|---|---|---|
| Structured extraction (Gemini + Instructor + Pydantic) | 97 CVs → validated schema | Every fact must cite a quote that is verified against the source text. Prompt-injection tests (hidden white text, visible "note to the AI") leaked no injected facts. |
| Embeddings | 9 configs (3 Voyage models × 3 dimensions) on 28 golden cases | voyage-3-large: recall@5 0.57, MRR 0.77 (a local baseline got MRR 0.37) |
| Chunking + metadata filters | whole CV vs recursive vs by section | By section: recall@5 0.57 → **0.77**. Filters for hard requirements: MRR 0.69 → 0.78 |
| Hybrid search (dense + Spanish BM25 + RRF) | exact-term queries vs profile queries | Exact terms: top-1 0.60 → 0.87. It **hurt** profile queries, so queries are routed by type instead of always going hybrid. |
| Workflow vs agent | same tools, same golden set | Workflow matched the agent's recall@5 (0.77 vs 0.72) with 1 model call instead of 6.5, at 4.4× lower cost. A name-swap bias test was clean. |
| LangGraph | checkpointer, human approval, crash recovery | `interrupt` before any side effect; resume from SQLite after a crash without re-running earlier nodes |
| Observability (self-hosted Langfuse) | traces, scores, cost per query, PII masking | A trace showed the agent spending its step budget reading CVs one at a time. Batching that tool: steps 8 → 4, recall@5 0.72 → 0.76, about 25% cheaper. |
| Guardrails | 52 recruiter messages, hand-labelled, split into calibration / held-out halves | Held-out: **7/7** discriminatory searches and **3/3** manipulation attempts caught, **0/12** legitimate searches blocked |
| Episodic memory | recruiter rejections with reasons as few-shot examples, 2 runs per arm | Repeat wrong recommendations of rejected profiles −43%, without dropping them where they *are* correct. The recall gain from run 1 **did not hold** on repeat (noise). |
| Right to deletion (Ley 1581) | one command, verified | Removes a candidate from Qdrant, caches, checkpoints, golden sets, memory and Langfuse traces, then proves nothing is left (tested on a copy of the data) |

## Layout

```
data_extraction/   Module 1: parsing (PDF/DOCX/MD), text vs vision routing, Gemini extraction with verified quotes, cost ledger
busqueda/          Modules 2-8: embeddings, Qdrant indexing, chunking, filters, RAG, hybrid search, tools,
                   workflow + agent (plain and LangGraph), tracing, guardrails, episodic memory, deletion
tests/             tracing (in-memory exporter), PII masking, guardrails, memory, deletion on a copy of the data
DECISIONS.md       the decision log: what was tried, the numbers, what was kept and why
COSTOS.md          every API run with tokens and cost
```

## Running it

The data is **not** in this repository: it is personal data, even though it's anonymised. To run the code you need your own `data/raw/CVs`, `data/raw/Vacantes` and a `.env`:

```
GEMINI_API_KEY=...
VOYAGE_API_KEY=...
LANGFUSE_PUBLIC_KEY=...      # optional (Module 7); self-hosted at LANGFUSE_BASE_URL
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=http://localhost:3100
```

```bash
pip install -r requirements.txt
python3 -m data_extraction.probar_muestra        # extraction on a 5-CV sample (request cap in code)
python3 -m busqueda.indexar                      # build the Qdrant collections
python3 -m busqueda.guardrails "Busco un contador menor de 30"
python3 -m pytest -q tests/                      # needs the data folder (deletion test copies it)
```

## Privacy

- Candidates appear in this repo only by their stable id (`cv-11`), never by name. Contact details in tests are invented.
- What goes to Langfuse passes a mask first (e-mails, Colombian phones, ID numbers). Names are not masked: that is a written product decision, because it needs NER and recruiters need the names.
- The guardrails refuse searches by protected attributes (age, sex, children/pregnancy, marital status, religion, origin, appearance, disability).

## Stack

Python 3.12 · Gemini (OpenAI-compatible API) · Instructor · Pydantic · PyMuPDF · Voyage AI · Qdrant · FastEmbed (BM25) · LangGraph · Langfuse (self-hosted, Docker) · pytest

Author: Esteban Lopez
