# Project costs

Every script that calls Gemini appends one row here automatically (`registrar_costo` in `data_extraction/extraer_cvs.py`).
Cost = tokens × price (`PRECIO_USD_POR_MILLON`: $0.75 input / $3.75 output per 1M, gemini-3.8-flash paid tier, through 2026-12-31; doubles 2027-01-01).
These are **our estimates from token counts**; the source of truth is Google AI Studio → Spend. Reconcile there from time to time.

Free tier (2026-10-22 → 2026-10-28 morning): $0. That covers the course exercises, the text-vs-vision comparison (2b), and the runs
that hit the 20/day quota or Google's 503 errors (see DECISIONS.md, "Retry incident").

| Date | Run | Schema | Model · thinking | Requests | Input tokens | Output tokens | Cost | Running total |
|---|---|---|---|---|---|---|---|---|
| 2026-10-28 | Sample (5 CVs), default thinking | cv-v4 | gemini-3.8-flash · default | 5 | 40,629 | 41,772 | $0.1871 | $0.1871 |
| 2026-10-28 | Thinking test: low on cv-15 | cv-v4 | gemini-3.8-flash · low | 1 | 6,679 | 1,029 | $0.0089 | $0.1960 |
| 2026-10-28 | Sample (5 CVs) | cv-v5 | gemini-3.8-flash · low | 5 | 41,159 | 5,070 | $0.0499 | $0.2459 |
| 2026-10-28 | Sample (5 CVs) | cv-v6 | gemini-3.8-flash · low | 5 | 41,654 | 5,256 | $0.0510 | $0.2968 |
| 2026-10-28 | Planted prompt-injection test (2 CVs) | cv-v6 | gemini-3.8-flash · low | 2 | 9,964 | 2,318 | $0.0162 | $0.3130 |
| 2026-10-29 | Sample (5 CVs) | cv-v7 | gemini-3.8-flash · low | 10 | 97,628 | 12,611 | $0.1205 | $0.4335 |
| 2026-10-29 | Diagnostic: why cv-65's quotes fail (v7) | cv-v7 | gemini-3.8-flash · low | 3 | 11,628 | 2,945 | $0.0198 | $0.4533 |
| 2026-10-29 | Sample (5 CVs) | cv-v8 | gemini-3.8-flash · low | 5 | 42,974 | 6,811 | $0.0578 | $0.5111 |
| 2026-10-29 | Full run (all CVs) | cv-v8 | gemini-3.8-flash · low | 98 | 651,144 | 125,244 | $0.9580 | $1.4691 |
| 2026-10-30 | Job postings: sample (5) | vac-v1 | gemini-3.8-flash · low | 5 | 17,802 | 3,201 | $0.0254 | $1.4945 |
| 2026-10-30 | Job postings: full run | vac-v2 | gemini-3.8-flash · low | 30 | 106,409 | 18,142 | $0.1478 | $1.6423 |
| 2026-11-17 | Module 2: embeddings for the golden-dataset eval | golden-v1 | Voyage (voyage-3-large, voyage-3.5, voyage-3.5-lite) | 45 | 1,537,551 | 0 | $0.1333 | $1.7756 |
| 2026-11-17 | Module 3: chunk embeddings (recursive + sections) | chunks-v1 | Voyage (voyage-3-large @ 1024) | 34 | 357,206 | 0 | $0.0643 | $1.8399 |
| 2026-11-17 | Module 3: RAG query embeddings | rag-v1 | Voyage (voyage-3-large) | 1 | 67 | 0 | $0.0000 | $1.8399 |
| 2026-11-17 | Module 3: RAG query embeddings | rag-v1 | Voyage (voyage-3-large) | 5 | 90 | 0 | $0.0000 | $1.8399 |
| 2026-11-17 | Module 3: RAG answers | rag-v1 | gemini-3.8-flash · low | 1 | 625 | 35 | $0.0006 | $1.8405 |
| 2026-11-17 | Module 3: RAG answers | rag-v1 | gemini-3.8-flash · low | 3 | 3,695 | 267 | $0.0038 | $1.8443 |
| 2026-11-17 | Module 3: RAG answers | rag-v1 | gemini-3.8-flash · low | 1 | 1,189 | 255 | $0.0018 | $1.8461 |
| 2026-11-17 | Module 5: workflow vs agent (3 cases) | m5-v1 | gemini-3.8-flash · low | 27 | 53,100 | 1,758 | $0.0464 | $1.8925 |
| 2026-11-17 | Module 5: workflow vs agent (3 cases) | m5-v1 | gemini-3.8-flash · low | 21 | 33,705 | 1,904 | $0.0324 | $1.9249 |
| 2026-11-17 | Module 5: workflow vs agent (todos cases) | m5-v1 | gemini-3.8-flash · low | 210 | 312,324 | 14,186 | $0.2874 | $2.2123 |
| 2026-11-17 | Module 5: bias test, twin embeddings | sesgo-v1 | Voyage (voyage-3-large) | 9 | 1,186 | 0 | $0.0002 | $2.2125 |
| 2026-11-17 | Module 5: bias test, agent runs | sesgo-v1 | gemini-3.8-flash · low | 21 | 31,360 | 959 | $0.0271 | $2.2396 |
| 2026-11-17 | Module 6: LangGraph workflow (28) + agent (5) | m6-v1 | gemini-3.8-flash · low | 64 | 95,734 | 8,821 | $0.1049 | $2.3445 |
| 2026-11-18 | Module 7: traced runs (workflow 28 + agent 6) | m7-v1 | gemini-3.8-flash · low | 65 | 93,622 | 8,151 | $0.1008 | $2.4453 |
| 2026-11-18 | Module 7: agent × 28 with batch leer_cv | m7-v2 | gemini-3.8-flash · low | 116 | 156,545 | 9,619 | $0.1535 | $2.5988 |
| 2026-11-18 | Module 8: guardrail end-to-end check (1 search) | m8-v1 | gemini-3.8-flash · low | 1 | 1,316 | 209 | $0.0018 | $2.6006 |
| 2026-11-18 | Module 8: agent × 28 with episodic memory | m8-v1 | gemini-3.8-flash · low | 125 | 203,545 | 10,323 | $0.1914 | $2.7920 |
| 2026-11-18 | Module 7: agent × 28 with batch leer_cv | m7-v2 | gemini-3.8-flash · low | 110 | 154,769 | 8,413 | $0.1476 | $2.9396 |
| 2026-11-18 | Module 8: agent × 28 with episodic memory | m8-v1 | gemini-3.8-flash · low | 121 | 191,060 | 11,211 | $0.1853 | $3.1249 |
| 2026-11-18 | Module 7: agent × 28 with batch leer_cv | m7-v2 | gemini-3.8-flash · low | 118 | 161,984 | 10,727 | $0.1617 | $3.2866 |
| 2026-11-23 | Web API: 1 searches | web-v1 | gemini-3.8-flash · low | 1 | 1,518 | 292 | $0.0022 | $3.2888 |
| 2026-11-23 | Public demo: fictitious CVs + pre-computed results | demo-v1 | gemini-3.8-flash · low | 10 | 7,422 | 9,989 | $0.0430 | $3.3318 |
| 2026-11-23 | Web API: 1 searches | web-v1 | gemini-3.8-flash · low | 1 | 1,160 | 240 | $0.0018 | $3.3336 |
| 2026-11-23 | Public demo: fictitious CVs + pre-computed results | demo-v1 | gemini-3.8-flash · low | 6 | 6,832 | 1,489 | $0.0107 | $3.3443 |
