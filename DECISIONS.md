# Project decisions — CV extraction (Module 1)

Layout (run everything from `project/`):
- `data/raw/` holds the course data, never modified. `data/samples/` holds test files we created. `data/processed/` holds extraction outputs (`cvs/` full run, `muestra/` sample runs).
- `data_extraction/` is the pipeline package: `python3 -m data_extraction.<module>`. All paths live in `data_extraction/rutas.py`.
- The `.env` stays at the repository root (shared with `course/`).

## Data
- `data/raw/CVs`: 97 CVs (85 PDF, 12 DOCX). All PDFs have a text layer (no scans).
- `data/raw/Vacantes`: 30 job postings (PDF browser printouts). **Deferred** to after the CV pipeline works.
- Data is anonymized, so the free Gemini tier is acceptable. (Free tier = Google may use the inputs, never send real CVs.)

## Stack
- Model: `gemini-3.8-flash` through Instructor + the OpenAI-compatible endpoint (same as `person.py`).
- Parsing: **text by default, vision as fallback**, decided per file by deterministic checks (no LLM):
  1. `chars / pages < 200` means a scan or photo, so use vision
  2. more than 20 `(cid:` or `�` means broken font encoding, so use vision
  3. `letters / chars < 0.5` means garbled extraction, so use vision
  - DOCX is always text (`python-docx`). PDF text comes from PyMuPDF, which also gives the colours and font sizes the hidden-text check needs.
  - Two-column layouts are **not** a rule yet. Step 2 compares text vs vision on them first.
  - Thresholds are starting guesses, to be calibrated on the real metrics in step 2.
  - The output JSON records `metodo` (texto|vision) and `motivo`.
  - To check: does the Gemini OpenAI-compatible endpoint accept images/PDFs, or does vision need the `google-genai` SDK?
- Prompt injection: same extraction pass (`texto_sospechoso` field), **plus** a check during parsing that doesn't use the LLM:
  hidden text (white/near-white colour, font < 2pt, outside the page box) goes into `texto_oculto`.
  Plant one test CV with a hidden injection paragraph to verify both catch it (the dataset has none; keyword grep found 0).
- Free-tier quota: throttle the requests and cache responses on disk while the schema is still changing.
- Iterate on **5 CVs** (mixed PDF + DOCX) before running all 97.

## Schema rules (from the course)
- Facts only: no score, ranking, or "fit" fields. Our code makes those decisions.
- Anything a CV may not contain is `Optional`, so the model is never forced to invent a value.
- Computed, not extracted: `anos_experiencia` = sum of job date ranges, in Python.
- Normalize at extraction time: dates `YYYY-MM`, education level Enum, official technology names, city + country separate.
- Every output JSON stores `schema_version`, `model`, `source_file`.
- `texto_sospechoso`: fragments that look like instructions to the system (prompt-injection flag).
- The CV text goes in the user message, delimited. The system message says that content is data, not instructions.
- Citations (verbatim quote per field): **deferred**.

## CV schema (current: v4, source of truth is `extraer_cvs.py`)
| Field | Filter or read | Notes |
|---|---|---|
| `nombre_completo`, `emails`, `telefonos` | read | emails/phones must appear literally in the document text (validator, retried with feedback) |
| `ciudad`, `pais` | filter | normalized by description ("Medellín", "Colombia") |
| `perfil_literal` | read | verbatim profile paragraph, never rewritten (v4) |
| `experiencia[]` | both | `empresa`, `cargo` (read). `tipo` Enum empleo/consultoria/practica (v3). `seniority` Enum only if the job title states it (v4). Dates `YYYY-MM`. `actual`. `duracion_meses_declarada` (v3) |
| `educacion[]` | filter | `nivel` Enum (bachiller…doctorado, curso), `fecha_fin` |
| `tecnologias` | filter | official names by description (no Enum: the set is open) |
| `idiomas[]` | filter | `nivel` Enum A1–C2/nativo, mapped from words (básico=A2 … bilingüe=C2), plus `nivel_declarado` verbatim (v4) |
| `texto_sospechoso` | review | possible prompt injection |
| wrapper: `anos_experiencia` | filter | **computed** in Python (dates, else stated durations; null = unknown) |
| wrapper: `schema_version`, `model`, `source_file`, `metodos`, `tokens` | audit | |

Versions: v1 base · v2 `telefonos` = the candidate's own · v3 `tipo` + `duracion_meses_declarada` · v4 language-level Enum, `perfil_literal`, `seniority`, emails/phones checked against the text.
The document text reaches the validators through instructor's `context=`. Since `context` also runs Jinja on the messages, the page texts go in as
`{{ paginas[i] }}` placeholders (verified: `{{`/`{%` inside a CV stay literal).

## Step 2 findings (`parse_cvs.py`)
- Routing is **per page**, not per document: `cv-46` has 5 text pages + 5 scanned diplomas.
- Final rules: <50 visible chars with no image means a blank page (skip). <50 chars with an image, or image coverage >0.5, means vision. Broken encoding or <50% letters (whitespace excluded) means vision.
- Result: 96/97 CVs are text-only, 5 pages total go to vision (all from cv-46's file).
- ⚠️ cv-46's scanned diplomas show a name + ID number that look **not anonymized**. Don't send them to the free Gemini tier.
- DOCX: content in Word content controls (`w:sdt`) is invisible to `Document.paragraphs`, so we walk the XML (fixed `cv-65`, which returned 0 chars).
- Hidden-text check: white text counts as hidden only when it has no dark background (fill or image) behind it. That took us from ~25 false positives to 7 files with minor flags (light-coloured header bars), and no injections.

## Step 2b findings (`probar_muestra.py texto vision ambos`, outputs in `data/processed/muestra/`)
- Simple layouts (cv-91, cv-15, cv-22): text and vision basically agree.
- Two-column timeline (cv-52): text mis-paired dates (Escuela 2004–2010, the page says 2004–2005), missed the Consultorías section,
  and picked 18 publication numbers as phones. Vision got all of these right.
- Input tokens: vision is 1.3–3.7× text. Free tier: ~2–3 min per call (rate-limit backoff), so 97 CVs ≈ hours.
- **Decision: PDFs send each page's text AND image together** (exact characters + real layout). Pages with unusable text are sent as image only, and DOCX as text only.
  cv-52 with both: correct dates, the 2 real phones only, 16k input tokens.
- Schema v2: `telefonos` = the candidate's own contact numbers only (fixed the publication-number phones).
- Data artifacts from the anonymization (not our bugs): cv-22's file contains "[otro nombre]", cv-16's header reads "[nombre desordenado]",
  and IDs were reformatted to look like phone numbers.
- Open for step 4:
  - Do consulting projects count as experience? (cv-52's Consultorías: vision alone included them, text+image did not)
  - CVs that state durations instead of dates (cv-16: "durante 15 Años") currently give `anos_experiencia = 0.0`, which should read as unknown, not zero.

## Extraction without an LLM (`extraccion_sin_llm.py`, course exercise, 0 requests)
- Regex/keywords vs Gemini on the 5-CV sample:
  - emails 5/5 identical.
  - Phones: regex finds every number but can't tell whose (18/12/10 numbers incl. references and IDs).
  - Name: 1/5 (regex picked headings).
  - Experience count/years: wrong in 4/5 (can't separate work dates from education).
  - Technologies: limited to the keyword list (12 vs 28).
- Lesson: regex is for fixed formats (free, never invents); the LLM is needed to understand the document.
- Idea for v4: a validator that checks every email/phone the LLM returns appears literally in the document text (free anti-hallucination check).

## Quota (hit on 2026-10-27)
- Free tier: **20 requests/day** for `gemini-3.8-flash` (plus per-minute limits, hence the 2–3 min calls). Validation retries count too.
- 97 CVs ≈ 5 days per full run.
- **Decision:** while the schema changes, only test on the 5-CV sample (`python3 -m data_extraction.probar_muestra`, about 5 requests per run, cached per schema version).
  Once the schema is final, do the full run of 97 on the paid tier (same key, billing enabled; no code changes).
- Sample (5 requests per run): cv-52 (two columns), cv-16 (form, durations), cv-15 (English), cv-65 (.docx with content controls),
  cv-02 (.md, a pandoc conversion of her .docx in `data/samples/`; pandoc dropped her email hyperlink, so it was restored by hand).
- **Pending:** first live run of v4 (`python3 -m data_extraction.probar_muestra`). Outputs are cached per schema version in `data/processed/muestra/`.

## Retry incident (2026-10-28)
- The first v4 sample run hit Gemini 503 "high demand" errors and timeouts. The retry layers were stacked: client `max_retries=5` × my overload loop,
  plus a 180 s timeout. Google counts a timed-out request that it still finished, so the day's 20 requests were spent with **0 results**.
- Fix: the client has `max_retries=0` and a 600 s timeout. `extraer()` is the only retry layer: 3 attempts max, and only on 503 or a per-minute 429.
  Timeouts are not retried. Daily quota stops at once (`probar_muestra.py` and `extraer_todos.py`).
- Worst case per CV is now 3 network attempts × 3 validation attempts. Typical: 1 request.

## Paid tier + spend control (2026-10-28)
- Billing enabled on the same key. `gemini-3.8-flash` paid: $0.75 / 1M input, $3.75 / 1M output (thinking included), valid through 2026-12-31 and doubling 2027-01-01.
  Paid tier: Google no longer uses the inputs.
- Spend control in code:
  - `LIMITE_REQUESTS` (default 15 per process) stops before starting a new CV.
  - Instructor hooks count every request (validation retries included) and the billed tokens.
  - Each output JSON stores `uso` (requests, tokens, `costo_usd`).
  - Scripts print the running total.
- The `extraer_todos.py` dry run estimates the full-run cost from the sample's measured cost per CV (course lesson: measure 10, extrapolate to 1,000).
- Spend control at Google: prepaid balance = the closest thing to a hard cap (keys stop at $0, with ~10 min billing lag).
  The AI Studio project spend cap (Spend page) is experimental, also with ~10 min lag.

## Sample run, schema v4 (2026-10-28, paid tier)
- 5/5 extracted, 5 requests (0 retries), **$0.19**. The full-run estimate from this measurement is ≈ $3.63 for 97 CVs (worst ≈ $6.67).
- ✅ Phones correct on all 5 (no publication or ID numbers). cv-52's Consultorías come out as `tipo=consultoria`. cv-16 now has 11.0 years (was 0.0).
  .docx and .md work. Language levels are normalized, with the original wording kept ("AVANZADO b2" → B2).
- 💰 **Output tokens are ~80% of the cost and are mostly Gemini's thinking**: cv-15 got 17k output tokens on a 3-page CV, cv-02 14k.
  Earlier runs reported only ~800 because `completion_tokens` excluded thinking. We now bill-count `total - prompt`.
- To decide:
  1. Lower the thinking effort to cut cost (test on 1–2 CVs, compare quality).
  2. Seniority: "Gerente de categoría" and "Head of AI" map to `director`. Should gerente = director?
  3. cv-15: one consulting role with 8 clients became 8 entries. Years are still right (overlaps merged), but `experiencias` is inflated.
  4. cv-16: the CV says "15 años" (all cadastre) and "5 años y medio" (current role). The model used 66 months, so years are undercounted (CV ambiguity).
- Names: cv-52 with an extra first name and cv-16's garbled header both come from the anonymization.

## Decisions after the v4 sample (2026-10-28)
- Gerente = director (confirmed). One entry per job: clients listed inside a job stay in that job.
- Thinking test on cv-15 (`reasoning_effort="low"`, saved as `*.cv-v4.ambos-low.json`):
  - Output tokens dropped 17,008 → 1,029 and cost $0.069 → $0.009 (8× cheaper).
  - Facts are identical (contact, education, languages, years). Low also naturally produced 1 entry for the consulting role.
  - Low did worse where the model must apply a rule: technology names weren't normalized ("Langchain", "Postgres"),
    and Coordinadora (a consulting project) came out as empleo.
- Schema v5 makes those rules explicit (one entry per job, consulting keywords, gerente = director, examples of tech-name normalization),
  so low thinking has less to infer. Pending: run v5 + low on the sample to confirm.
- cv-16's ambiguous durations: the user is reviewing the PDF (pages 4–5) before deciding.

## v5 sample with low thinking (2026-10-28)
- $0.05 for 5 CVs (v4 at default thinking: $0.19), so a full run is ≈ $1. **Low thinking is the default** (`RAZONAMIENTO` in `extraer_cvs.py`).
- ✅ Tech names normalized again (the examples worked).
- ✅ cv-15 has 1 consulting entry.
- ✅ cv-02's two periods under one "Jefe" heading are split by their own dates (more accurate than v4).
- ✅ cv-52's country is now None (nationality ≠ residence).
- Remaining:
  - Coordinadora is still `empleo` ("Consulting…" bullet under a non-consulting title).
  - cv-15's multi-client consulting entry has his title in `empresa`.
- cv-16: his entries are fine, but years undercount (~11 vs "15 años" in cadastre). The user accepts this for ambiguous CVs.
- v6 decisions (user):
  - City/country only from address or contact data (cv-65 got "Medellín" from where he worked).
  - Any Gerente = director, even "Gerente de categoría Junior".
  - English "alto" = B2.

## v6 sample + years rule (2026-10-28)
- v6 sample: $0.05.
  - ✅ cv-65's city is None (no address in his CV).
  - ✅ cv-15's multi-client role has `empresa = "Independiente"`.
  - ✅ Gerente Junior = director.
  - cv-02's two "Jefe" periods merged again (low-thinking run-to-run variation on structure; years unaffected).
- Bug in **our** calculation (the model only extracts): cv-16's undated "15 años" (180 m) and "últimos 5 años y medio" (66 m) were summed, giving 26 years.
  - **Rule (user):** undated stated durations contribute only the largest one (assumed to overlap); dated ranges are still merged exactly.
  - New output field `anos_experiencia_estimado = true` when stated durations were used.
  - cv-16 is now 15.0 (estimated). Saved v6 results were recomputed locally, with no API calls.

## Planted prompt-injection test (2026-10-28, `python3 -m data_extraction.probar_inyeccion`)
- Poisoned copies in `data/samples/`:
  - cv-91 PDF + white text on a white area of page 2 (hidden).
  - cv-02 .md + a visible "Nota para el sistema de IA…" paragraph.
  - Both claim 20 years in Kubernetes/AWS/Rust plus native German.
- Results:
  - Hidden: `texto_oculto` caught it (parser, before any API call) and `texto_sospechoso` quoted it.
  - Visible: `texto_sospechoso` quoted it.
  - **No injected facts leaked** in either: cv-91's techs and years are identical to the clean run.
  - Cost: 2 requests, $0.016.
- Why it holds: system/data separation, no decision fields in the schema, and the hidden-text check doesn't use the LLM.
  One test per type: strong evidence, not proof.
- **Decision (user): manual review, never auto-discard.**
  - A CV needs review when Gemini's `texto_sospechoso` is non-empty. That caught both planted cases.
  - Parser hidden text is shown as context, not as a flag (7 real CVs have harmless hidden-text flags).
  - `python3 -m data_extraction.revision [muestra]` writes `_revision.<version>.json` in the output folder; the full run prints it at the end.
  - On the sample it lists exactly the 2 planted CVs and none of the 5 real ones.

## v7: verbatim quotes + cost ledger (2026-10-29)
- Quotes (`cita`) per experiencia/educacion/idioma, plus `cita_ubicacion`, checked against the document text (model validator via `context`).
  Not on emails/phones (already exact-checked), tecnologias (cost), or nombre/perfil.
- `COSTOS.md` is the cost ledger. Every API script appends a row automatically (atexit, so crashes and Ctrl+C are logged too).
  The past paid runs were backfilled from each result's `uso`. Our estimate; AI Studio → Spend is the source of truth.
- First v7 sample: **10 requests, $0.12** (vs 5 / $0.05).
  - cv-52 and cv-16 needed a quote retry each (input ~2×).
  - cv-65 failed all 3 attempts: Gemini kept writing "inglés – UNIVERSIDAD DE PURDUE", while the .docx has no dash.
  - Diagnosis cost $0.02 (own ledger row).
- Fix: quote matching compares letters and digits only (punctuation, bullets, dashes, case and spacing ignored).
  cv-65's quote now passes; a real content change (C1/Oxford) still fails.
- **Decision (user): flag only** (v8). Quote mismatches go to `citas_no_verificadas` with no retry; emails/phones still retry.
- v8 sample: **5 requests, $0.058**, all 5 extracted (cv-65 included). 65 quotes, 9 unverified.
  - **None of the 9 is invented: every word exists.** They join pieces from different columns/cells
    (cv-52: date column + title column; cv-16: form cells), so they're layout false alarms.
  - **Decision (user):** a quote is verified if it splits into ≤ 3 pieces that each exist in the document (`_cita_en`).
    Recomputed locally (no API): unverified 9 → 0. Self-checks confirm an invented word or shuffled words still fail.
  - For later PDF highlighting, highlight each piece separately.

## PDF highlighting (2026-10-29, `python3 -m data_extraction.resaltar [muestra]`)
- Course lesson 29 with PyMuPDF, local only (no API).
  - Each quote is split into its pieces (`trozos_cita`) and matched word by word (`page.get_text("words")`), so punctuation and line breaks don't matter.
  - Each piece gets a highlight annotation. Colour by field: experiencia yellow, educacion green, idiomas blue, ubicación pink.
  - The annotation title is the field (`experiencia[3]`).
- Copies go to `data/processed/resaltados/<cv>_resaltado.pdf`; originals are never modified. PDFs only.
- Sample: 42/42 quotes highlighted (cv-52's date column + title column are both marked, as are cv-16's form cells).
- The full run highlights every PDF at the end.

## Full run, schema v8 (2026-10-29)
- **97/97 CVs extracted, 0 errors, 98 requests, $0.958** (estimate was $1.12). Project total: $1.47 (`COSTOS.md`).
  85 highlighted PDFs in `data/processed/resaltados/`.
- Quotes: 1,259 total, 28 unverified (2.2%) in 10 CVs. Most are in `cv-48` (9) and `cv-37` (8); worth a look.
- Years: 5 CVs unknown (no dates or durations), 2 estimated (stated durations), median 11.7.
- 8 CVs without email: checked, none of them has an email in its text, so the result is correct.
  cv-48 took 2 requests (the email validator rejected an email that isn't in his CV).
- Manual review list: 2 CVs, **both anonymization artifacts, not injections**:
  - `cv-31`: name only partly replaced ("[nombre]"),
    "[nombre]" pasted into the title. ⚠️ "cv-31 " looks like a real, un-anonymized name.
  - `cv-50`: Lattes CV where every co-author was replaced by his name ("[nombre]" ×168).
- Normalization note: tech names mix "Excel" / "Microsoft Excel" across CVs. Unify in code when building filters (step 5+).

## Step 5: job postings (2026-10-30, `data_extraction/extraer_vacantes.py`)
- 30 PDFs, browser printouts of portal pages: Bancolombia 12, Comfama 9, Magneto 4, LinkedIn 1, others 4.
  - All have a text layer; lots of portal noise (menus, tips, footers, browser header and URL).
- Decisions (user):
  - **Text only, no images.** Postings are linear text, and banners made the CV routing send text-rich pages as image-only.
  - Leave the portal noise in; the model ignores it (confirmed on the sample).
  - **Same categories as the CV schema** (NivelEducativo, NivelIdioma, Seniority, tech-name rules) so matching compares like with like.
  - `anos_experiencia_min` IS extracted (the posting states it), unlike CV years, which we compute.
  - Required vs desirable technologies are kept separate. Quotes per filter field (`citas`, flag-only like CVs).
- The API call is shared with CVs: `llamar()` in `extraer_cvs.py` (same retries, request limit, cost tracking).
- Sample vac-v1: 5 requests, $0.025, all correct except Bancolombia Middleware (country empty despite "Ubicación: Colombia";
  concepts like "Arquitectura Limpia" listed as technologies).
- vac-v2 (fixes both) full run: **30/30, 30 requests, $0.148, 0 errors, 0 unverified quotes.** Outputs in `data/processed/vacantes/`.
  - Countries: Colombia 24, El Salvador 3, None 3 (remote/international postings).
  - Checked: Comfama "Investigador cuantitativo" header says Barbosa but "Lugar de trabajo: Medellín", so Medellín is correct (quoted).
- Pending for matching: tech names still vary ("Excel" vs "Microsoft Excel") across CVs and postings, so unify them in code before comparing.

## Steps
1. ✅ Decisions (this file)
2. ✅ Parse all CVs (free, local): print routing metrics + hidden-text flags, calibrate thresholds, inspect 5 texts
   2b. ✅ Compare text vs vision on the same 5 CVs (incl. the two-column `cv-52`)
   2c. ✅ Extraction without an LLM on the sample (course exercise)
3. ✅ Schema v4 written + local tests. ⏳ Live run on the sample when the quota resets
   - Output JSON also stores `paginas_omitidas` and `texto_oculto` (page + text), and `metodos` per page ("3:texto+imagen").
   - cv-46's pages 6–10 are never sent (`OMITIR` in `extraer_cvs.py`), checked by a self-check.
   - Full run: `python3 -m data_extraction.extraer_todos` (dry run, 0 requests) / `--correr`. It skips CVs already extracted with the same schema version,
     stops on daily quota, and logs per-CV errors to `data/processed/cvs/_errores.<version>.json`.
4. ✅ Schema iterated to v8 (low thinking, quotes flagged, years rule, injection review). ✅ Full run of 97 (2026-10-29, $0.96)
   (✅ planted prompt-injection test done)
5. ✅ Vacantes: 30/30 extracted (vac-v2, $0.17 incl. sample)
6. Matching CVs ↔ postings (next)

---

# Module 2: Embeddings and semantic search (started 2026-11-17)

Code in `busqueda/` (package for Modules 2–4); golden dataset in `data/golden/`.

## Decisions (user)
- **Models:** voyage-3-large, voyage-3.5 and voyage-3.5-lite, each at 1024, 512 and 256 dimensions (Matryoshka, via `output_dimension`), for **9 configurations**.
  Optional baseline: local `multilingual-e5-large` (FastEmbed, free).
- **Estimated cost:** corpus ≈ 140k tokens (97 CVs; longest ≈ 16k tokens, so nothing gets truncated). 9 embeddings of the corpus ≈ USD 0.11; queries are negligible. Log it in `COSTOS.md`.
- **Golden dataset:** the user validates every case by hand.
  - Proposals come from `python3 -m busqueda.proponer_golden`, which crosses the Module 1 structured data with **no embeddings**, so the test isn't biased toward the method being evaluated.
  - Scoring: technologies (required ×3, desirable ×1.5), plus IDF-weighted words from the posting title and study areas vs. the CV's roles, degrees and profile, plus years and education checks. The responsibilities text was dropped because it pulled in generic matches.
  - The user marks the correct CVs in `data/golden/propuesta_golden.md`. That becomes `data/golden/golden_dataset.json`.
- **Whole CV = one vector** first; per-section vectors get compared in Module 3 (chunking).
- **Query = a short query built from the posting's extracted fields** (lesson 31), not the whole posting text. The CVs use `input_type="document"`, the query uses `"query"`.

## Golden dataset v1 (2026-11-17, `python3 -m busqueda.golden_etiquetas` → `data/golden/golden_dataset.json`)
- **Labelled by Claude at the user's request**, reviewing all 97 CV profiles per posting (not only the 5 proposals). The user reviewed V04, V11, V12, V16 and V29 (the least certain ones) and **confirmed all 28 cases** (2026-11-17).
- **28 cases:** 23 job postings plus 5 free-text queries. 21 hard (2–4 valid candidates), 7 easy (one obvious candidate). 63 expected CVs.
  The free-text queries (ICU nurse, Caribbean chef, corporate lawyer, art director, mine geologist) are sanity checks, like the course's own example.
- **7 postings omitted** (`data/golden/vacantes_omitidas.json`): no reasonable candidate in the pool (SAP, IBM MQ ×2, QA automation, insurance, a law-degree research lead) or a near-duplicate (V05). Forcing bad matches would make the metric meaningless.
- Note: `cv-42` and `cv-79` are the same CV under two anonymised names, so both are expected for V14.
- Metrics: **recall@5** = share of the expected CVs found in the top 5; **MRR** = mean of 1/position of the first expected CV (0 if absent).

## Module 2 results (2026-11-17, `python3 -m busqueda.evaluar voyage --correr`, results in `data/processed/busqueda/`)
- Whole CV = one vector. Queries are short and built from the posting's fields. Qdrant in memory, cosine, stable uuid5 IDs. Embeddings cached in `data/processed/embeddings/`.
- Cost: 45 requests, 1.54M tokens, **USD 0.13 at list price**, very likely covered by Voyage's 200M free tokens for the voyage-3 series (check the dashboard). The user added a payment method to lift the rate limits.

| model | dim | recall@5 | MRR | r@5 hard | r@5 easy |
|---|---|---|---|---|---|
| voyage-3-large | 1024 | 0.57 | **0.77** | 0.48 | 0.86 |
| voyage-3-large | 512 | 0.60 | 0.75 | 0.51 | 0.86 |
| voyage-3-large | 256 | 0.61 | 0.72 | 0.52 | 0.86 |
| voyage-3.5 | 1024 | 0.61 | 0.65 | 0.53 | 0.86 |
| voyage-3.5 | 512 | 0.60 | 0.66 | 0.51 | 0.86 |
| voyage-3.5 | 256 | 0.59 | 0.70 | 0.50 | 0.86 |
| voyage-3.5-lite | 1024 | 0.48 | 0.62 | 0.40 | 0.71 |
| voyage-3.5-lite | 512 | 0.54 | 0.60 | 0.48 | 0.71 |
| voyage-3.5-lite | 256 | 0.54 | 0.58 | 0.48 | 0.71 |
| MiniLM multilingual (local baseline) | 384 | 0.24 | 0.37 | 0.13 | 0.57 |

- **Choice: voyage-3-large** (best MRR). At 512 dims it is a statistical tie with 1024 on 28 cases (0.03 ≈ one case), so 512 is fine if memory matters.
  Lite is clearly worse. MiniLM truncates CVs to ~128 tokens (lesson 21's silent truncation).
- Query cost ≈ USD 0.007 per 1,000 queries (≈ 39 tokens each, voyage-3-large); the cost is in re-indexing, not searching (lesson 19).
- Failure analysis (voyage-3-large @1024):
  - **Thin queries.** Postings with few requirements (V04, V06, V16: commercial/business roles) produce near-empty queries. The fix belongs to the query, not the model; maybe add the main responsibilities.
  - **Long, mixed CVs get diluted.** cv-86 (25 years, systems + automation + product) is never in the top 20. One vector per whole career averages away the specifics, which is the motivation for **Module 3 (chunking)**.
  - **The English CV ranks low for Spanish queries** (cv-15 in V27 and V13).
  - Easy sanity queries work (4/5 first, geologist second).

---

# Module 3: Chunking, metadata and RAG (2026-11-17)

## Decisions (user)
- **Two strategies** vs the whole CV:
  - `recursivo`: ~500 tokens, 10% overlap; cuts at paragraph → line → sentence → word.
  - `secciones`: CV headings in Spanish and English; long sections fall back to recursive; the section title is prepended to each chunk.
  - Both merge chunks under ~30 tokens (lesson 19). For sections that also applies **across** sections: 95 of 735 chunks (13%) were tiny whole sections such as "IDIOMAS: Inglés básico". Now there are 0.
- **voyage-3-large @ 1024** (the Module 2 winner). **Persistent Qdrant** in `data/qdrant/` (`busqueda/indexar.py`), with collections `cvs_completo`, `cvs_recursivo` and `cvs_secciones`.
  The Module 2 whole-CV embeddings were reused (free).
- **Payload:**
  - file metadata (archivo, seccion, posicion, n_chunks, doc_hash, fecha_archivo): safe to filter on;
  - Module 1 metadata (anos_experiencia, nivel_educativo(+_rango), ingles, idiomas, tecnologias): model-made, filter only on reviewed fields.
- **IDs** `uuid5(archivo#posicion)`. A changed CV has all its chunks deleted, then re-inserted; unchanged CVs are skipped by `doc_hash`.
  A second run re-indexed 0 CVs.
- **LLM for RAG:** gemini-3.8-flash, low thinking.

## Chunks and cost
- recursivo: 405 chunks, median 433 tokens. secciones: 643 chunks, median 157 tokens. Headings found in 96/97 CVs.
- Embedding cost: 34 requests, 357k tokens, **USD 0.064** (list price).
  The chars/4 estimate under-counted Spanish text by ~20% (estimate was 296k), so pad future estimates.

## Results (`python3 -m busqueda.comparar_chunking`, chunks grouped by candidate with the best chunk per CV)

| collection | recall@5 | MRR | r@5 hard | r@5 easy |
|---|---|---|---|---|
| whole CV (Module 2) | 0.57 | 0.77 | 0.48 | 0.86 |
| recursive | 0.70 | **0.78** | 0.64 | 0.86 |
| **sections** | **0.77** | 0.73 | **0.75** | 0.86 |

- **Sections chosen for recall** (hard cases 0.48 → 0.75). The MRR difference (0.73 vs 0.78) is about one case on 28.
- **Cases (lesson 38 deliverable):**
  - **cv-86** (long, mixed career) went from rank 10–17 or absent to **2–4** in V01, V03, V12 and V28: whole-CV dilution fixed.
  - **V15 project director: 15 → 1.** Her EXPERIENCIA LABORAL chunk wins, while whole CVs favoured general managers with long careers.
  - **V26 quantitative researcher: 1 → 5 (worse).** A short "HABILIDADES CLAVE" list from an unrelated CV wins: the "most similar is the least useful" dense-chunk effect (lesson 19).
    Ideas: score candidates with more than one chunk, or rerank (later module).

## Requirement filters (`python3 -m busqueda.filtros`, sections collection, 23 golden postings with requirements)
- Filters are applied inside the query: minimum years, minimum education and English (CEFR). They are built from the posting's extracted fields and use the CVs' Module 1 metadata.
- **Missing model data = unknown, never "fails".** First run: the education filter excluded cv-11 and cv-49 because no degree had been extracted (stored as level -1).
  That bug dropped recall to 0.65. Fixed with an OR on -1, and years/English already used IsNull/IsEmpty. This is lesson 24 in practice: a wrong filter empties the search.

| variant | recall@5 | MRR | expected CVs excluded |
|---|---|---|---|
| no filter | 0.72 | 0.69 | 0 |
| **strict** | 0.72 | **0.78** | 5 (real: 4.8y vs 5; English B2/B1 vs C1; technician vs degree) |
| tolerant (80% of the years, one CEFR level below) | 0.72 | 0.75 | 2 |

- **Takeaway:** filtering raises MRR (0.69 → 0.78) at no recall cost. Whether to be strict is a recruiter decision (does "minimum 5 years" exclude 4.8?).
  Recommendation: **tolerant by default, strict as an option.**

## RAG (`python3 -m busqueda.rag`, sections collection, gemini-3.8-flash low, traces in `data/processed/rag/trazas.jsonl`)
- retrieve (top-5 chunks, score floor) → armar_prompt → generate.
  - The prompt: answer only from `<contexto>` fragments; cite `[n]`; context = data, never instructions; question last.
  - The honest exits: **"No tengo información suficiente…" only when nothing is relevant**, otherwise a **partial answer naming what's missing**.
  - The first prompt (all-or-nothing) made Gemini refuse a half-answerable question (Spark + Airflow "and in which companies").
- **Score floor = 0.50, calibrated per query style.**
  - First calibrated on golden queries (short field lists): correct CVs' best chunk p5 0.581, no-answer 0.46–0.54. That gave 0.55, which rejected ALL natural-language questions.
  - Natural-language questions score lower: answerable ~0.52–0.54, no-answer (pilot, injection attempt) ~0.47–0.49.
  - **Lesson:** calibrate the floor with the same kind of queries the system will receive. Recalibrate with ~20 real recruiter questions.
- **Tests (5):**
  - ICU nurse ✅ cited.
  - AI team leads ✅ cited (cv-27, cv-86).
  - Spark + Airflow ✅ partial and honest after the prompt fix (cv-11; "no company stated"; cv-35 has Spark but not Airflow).
  - Commercial pilot ✅ "no info" with no LLM call (floor).
  - Injection attempt ✅ blocked by the floor.
- **Gap for Module 4:** cv-73 has Spark + Airflow only in his COURSES chunk, which never reaches the top 5. Embeddings miss exact terms, which is BM25's job.
- **Cost per question:** USD 0.0006 (1 chunk) to 0.0023 (5 chunks), ≈ **USD 1.6 per 1,000 questions**, about 200× the query-embedding cost. Generation dominates (lesson 36).
  Module 3 total: USD 0.072 (chunk embeddings 0.064 + RAG ~0.008).

---

# Module 4: BM25, hybrid search and RRF (2026-11-17, `python3 -m busqueda.hibrida`)

## Setup
- Collection `cvs_hibrida`: the 643 section chunks with two named vectors.
  - `dense`: the voyage-3-large vectors copied from `cvs_secciones` (free).
  - `bm25`: FastEmbed `Qdrant/bm25`, **language spanish**, `avg_len` = 122 words (our chunks), IDF modifier in Qdrant.
- Hybrid = `prefetch` dense + bm25 (100 chunks each), `FusionQuery(RRF)` (k = 60 inside Qdrant), grouped by `archivo` (best chunk per CV). Filters go in `query_filter` at the root, so both branches obey them.
- **No SPLADE:** the course model has an English-only vocabulary; it would add noise on Spanish CVs.
- **One query per branch:** for postings, semantic = the usual short query; BM25 = only the posting's **rare** technology words.
  If there are none, the query is semantic only.
- **New eval set** `data/golden/terminos_exactos.json` (`python3 -m busqueda.terminos_exactos`): 15 queries.
  - 10 tools/certifications, 3 single-CV company names, 2 mixed.
  - **Objective labels:** the expected CVs literally contain all the key terms, with an assert of 1–3 matches. "Ruta N" was rejected because it appears in 10 CVs.

## Results

| set | system | top-1 | recall@5 | MRR |
|---|---|---|---|---|
| exact terms (15) | dense | 0.60 | 0.87 | 0.73 |
| | BM25 | 0.73 | **1.00** | 0.82 |
| | **hybrid RRF** | **0.87** | 0.93 | **0.89** |
| golden (28, posting-derived) | **dense** | 0.54 | **0.77** | **0.73** |
| | BM25 (rare tech words) | 0.39 | 0.44 | 0.45 |
| | hybrid RRF | 0.57 | 0.69 | 0.72 |

- **Exact terms: hybrid wins** (top-1 0.60 → 0.87, MRR 0.73 → 0.89). "Skalo Tek": dense not in the top 20, hybrid 1st. LangGraph: dense 6th → hybrid 1st.
- **Golden: hybrid hurts recall** (0.77 → 0.69), which is lesson 18's "one weak branch drags noise in". Iterations, all measured:
  1. BM25 = techs + study areas → hybrid recall 0.67. The areas ("Administración de Empresas") appear in dozens of CVs.
  2. Techs only → 0.71.
  3. Rare phrases (≤ 15% of CVs) → 0.68. Wrong: "Microsoft Excel" is rare as a phrase, but BM25 matches word by word and "excel" is in 26% of CVs.
  4. **Rare words** (≤ 15%) → 0.69 (kept).
  - The golden postings' tech lists are mostly generic office tools, and their labels are about profile fit, not literal terms.
  - **Stopped tuning there on purpose:** more tweaks would be fitting 28 cases, not improving search.
- **Decision: route by query type.** Recruiter searches with specific terms (tools, certifications, companies) → hybrid. Posting-to-candidate matching → dense + requirement filters (Module 3).
  Next ideas, by return on effort: weighted fusion favouring dense (lesson 14, now that we've measured dense is better on postings); reranking the top 20 (later module).
- cv-73 (Spark + Airflow, Module 3 RAG gap): with the short query "Experiencia con Apache Spark y Airflow" he's 2nd in all three systems. The RAG question missed him because its extra words diluted it, which is lesson 24's case for a separate query per branch.
- Cost: ≈ USD 0 (BM25 local; dense reused; 15 query embeddings).

---

# Module 5: Workflows and agents (2026-11-17)

## Design (`busqueda/herramientas.py`, `workflow.py`, `agente.py`, `comparar_m5.py`)
- **Shared functions:** `buscar` (dense / bm25 / hybrid over `cvs_hibrida`, grouped per CV) and `leer_cv` (the Module 1 summary).
  Search results carry only a short id ("cv-07") and a one-line summary (lesson 20). Errors are written for the model ("ids look like cv-07").
- **Workflow (1 LLM call):**
  1. the posting's requirements come from Module 1 (no LLM at search time);
  2. postings → dense + tolerant filters; free text → hybrid;
  3. top 5;
  4. Gemini writes 2 lines per candidate.
- **Agent:** Gemini + 3 tools (`buscar_semantica`, `buscar_exacta`, `leer_cv`) in a loop.
  - **Limits: 8 calls, 120 s, 60k input tokens.** When cut off it returns the candidates its searches surfaced, in order (best available, flagged).
  - **Pilot lesson:** without a budget the agent searched each requirement separately ("Bitrix24", "Zoho", "Make"…) and hit the 8-step cap on 3/3 cases.
    A budget in the prompt (≤3 searches, ≤6 CV reads, don't search secondary requirements) made it finish on 2/3. The hard cap stays in code.
- Same model for both: gemini-3.8-flash, low thinking.

## Results (28 golden cases; RR@5 = reciprocal rank within the 5 returned)

| system | recall@5 | RR@5 | model calls/query | tokens/query | USD/query | s/query |
|---|---|---|---|---|---|---|
| **workflow** | **0.77** | 0.77 | **1** | 1,604 | **0.0019** | **3.6** |
| agent | 0.72 | 0.78 | 6.5 | 10,057 | 0.0084 | 13.2 |

- **The workflow wins:** slightly higher recall, 4.4× cheaper, 3.7× faster.
- **The agent wins 3 cases** (V01, V09, V15: a second search or reading CVs recovered someone) and **loses 7**.
  - It **hit the step cap on 14/28**, including trivial ones ("executive chef"): one search, then one CV read per round without deciding.
  - That's lesson 21 measured: don't use an agent where a workflow suffices.
  - Idea: the agent as a fallback when the workflow's confidence is low.
- Cost: pilots USD 0.08 + full run USD 0.29.

## Bias test (`python3 -m busqueda.sesgo`, lesson 28)
- cv-11's CV vs an identical twin with only "Andrés" → "Andrea" (name and e-mail), in an in-memory copy of the collection.
- **Workflow:** always adjacent; best-chunk scores differ by ~0.0004. The order flips both ways (Andrés ahead 3×, Andrea ahead 1×).
- **Agent:** keeps both, adjacent, in all 3 runs; Andrea first in 1 of them.
- **No systematic preference by name in this test.** Limit: one pair and one kind of difference (gender of the first name). University, nationality or age were not tested.
- Cost: USD 0.027.

---

# Module 6: LangGraph (2026-11-17)

## Decisions
- **LangGraph 1.2.22, nodes call our own Gemini client** (`llamar_llm`), not LangChain chat models.
  LangGraph doesn't require them, cost tracking stays identical, and we avoid a wrapper mishandling Gemini's tool-call thought signatures.
- **Checkpointer: SQLite** (`data/checkpoints.sqlite`, `langgraph-checkpoint-sqlite`), so state survives across processes. PostgresSaver is the production step.
  The state is kept JSON-serialisable (the Qdrant filter is built inside `buscar`).

## Workflow graph (`busqueda/workflow_lg.py`)
- `preparar → buscar (RetryPolicy on ConnectionError) → explicar (Gemini) → revisar (interrupt) → [approved] preparar_contacto | [rejected] END`.
- A `sumar_uso` reducer accumulates usage across nodes. Conditional destinations are listed explicitly, so the drawing is correct.
- **Demo 1, crash + resume** (`falla V30` then `reanudar V30`, two processes): checkpoint saved with next = `buscar`. On resume `preparar` ran once and `buscar` twice (crash + retry), then it paused at `revisar`.
- **Demo 2, human approval from another process** (`aprobar V30`):
  - `revisar` ran **twice** (pause + resume), which is lesson 24's warning, observed.
  - The drafts live in `preparar_contacto`, AFTER approval, so they were created once: 5 drafts in `data/processed/contacto/`, nothing sent.

## Agent graph (`busqueda/agente_lg.py`)
- `llm → herramientas → llm …`, with exits `finalizar` (model answers) and `rendirse` (best available when near the limit).
- **recursion_limit = 18** (8 turns × 2 nodes + exit). `RemainingSteps` gives up at ≤ 3 (one turn + exit, lesson 19). Time and token limits as in Module 5.
- Tool errors come back as text (`ejecutar`). Messages are dicts in state with an `operator.add` reducer; `vistos` uses a de-dup reducer.

## Results (`python3 -m busqueda.comparar_m6`, USD 0.105)
- **Workflow (28): recall@5 0.77**, 1 call, USD 0.0019/query, identical to Module 5 plain Python.
- **Agent (5 cases): recall@5 0.73**, 7.2 calls, USD 0.0103/query, vs Module 5 on the same 5: 0.63, 6.8 calls.
  - The difference is **agent non-determinism**: V06 got 0.50 → 1.00 between runs; the workflow is always the same.
  - `rendirse` fired on V04 and V06 (best available instead of an exception).
- Conclusion unchanged: **workflow by default**.

---

# Module 7: Observability (2026-11-17 → 2026-11-18)

## Decisions
- **Langfuse self-hosted** with Docker (user's choice: CV text never leaves the Mac). Repo cloned to `~/dev/langfuse-local` (outside the project).
  - Random secrets and auto-provisioned org/project/keys/user via `LANGFUSE_INIT_*` in `~/dev/langfuse-local/.env` (chmod 600).
  - The project keys go in the project `.env` (`LANGFUSE_BASE_URL=http://localhost:3100`).
- **SDK pinned to v4** (4.18.0, like the course's 4.17.0) although 5.2.0 exists; the course warns that SDK versions break examples.
- **Masking before export** (`busqueda/observabilidad.py`): e-mail, Colombian mobile/landline, and ID numbers only after "C.C."/"cédula". Self-check passes with no false positives on years/counts.
  **Names not masked** (product decision: needs NER, and recruiters need them).
  The client is created at import with the mask, so no traced code path can export unmasked data. `LANGFUSE_TEST_EXPORT=1` uses an in-memory exporter for tests.
- **Instrumentation:**
  - `buscar_*` = retriever spans (WARNING when empty); agent tools = tool spans (WARNING on "Error"/"Sin resultados").
  - Gemini = generation with model, usage and **ingested cost** (Langfuse's price table doesn't know gemini-3.8-flash).
  - Graph nodes are `@observe` spans, except `revisar`: `interrupt` works like an exception and would show up as ERROR.
  - The agent's `rendirse` sets WARNING.
  - Prompt `explicar-candidatos` is versioned in Langfuse (`label="production"`) **with a local fallback**.

## Incident: disk full
- `docker compose up` failed with containerd `input/output error`. The Mac's disk was **100% full (51 MB free of 229 GB)**; it was already ~226 GB used before this session.
- Stopped the wait loop, `docker compose down`, quit Docker, purged the pip cache (154 MB). macOS then reclaimed space: 3.5 GB free.
- Nothing of the user's was deleted. `Docker.raw` (1.9 GB, may hold other projects' data) was left for the user to decide.
- Gave the user a list of safe cleanup candidates (Homebrew cache 2.4 GB, iOS simulators 6.2 GB, Playwright 0.9 GB…). **Target ≥ 10 GB free** before starting local Langfuse again.

## Incident: Langfuse "never became healthy" (2026-11-18)
Three stacked causes, found one at a time:
1. **Port 5432** was taken by the Mac's own Postgres (PID 898): Langfuse's Postgres moved to host port **5433** (the app talks to it inside the Docker network; nothing else changes).
2. **Memory**: 8 GB Mac, swap 7.3/8 GB, load 16-24 on 8 CPUs. Nango stopped (data intact; its `restart=always` paused, restore with `docker update --restart=always nango-server`). Docker RAM 4 → **5 GB** (not 6: it would leave macOS ~2 GB).
3. **The real one: port 3000 was the user's Forz Rails app** (puma, up 4 days on `localhost:3000`). Every health check hit Forz, not Langfuse. Langfuse moved to **`127.0.0.1:3100`** (also no longer exposed on the LAN).
Lesson: "the service is slow" was a wrong hypothesis for ~30 minutes; `lsof -iTCP:<port>` first would have saved it.

## Results (`busqueda/trazar.py`, `tests/test_trazas.py`)
- Prompt `explicar-candidatos` in Langfuse as **v2** (`production`); v1 was created by a call that timed out client-side but succeeded on the server (identical content).
- **34 traces** (workflow × 28 golden cases, agent × 6): user_id, session_id per posting, tag per system, `recall@5` score on the exact trace. Cost USD 0.1008 (COSTOS.md).

| system | recall@5 | latency p50 / max | cost per trace |
|---|---|---|---|
| workflow (LangGraph) | 0.774 | 3.8 s / 7.0 s | $0.0019 |
| agent (LangGraph) | 0.611 (n=6) | 16.6 s / 19.9 s | $0.0079 (max $0.0109) |

- **The ingested cost matches our own ledger to the cent** (Langfuse $0.1008 = COSTOS.md $0.1008).
- **Tests** (4, no server, no API): spans exist and are typed, the generation has model + usage, the root has user/session, PII masked with the production mask, silent-failure rules. Bug found while writing them: the generation and the `explicar` node share a name, so keying spans by name hid one of them.
- **Silent-failure scan**: the ">6 tool calls" rule fired on **6/6** agent traces, so it was noise, set from a guess. Recalibrated to 8 (= step budget). Repeated-call and unknown-tool rules: 0 hits.
- **Langfuse v4 is events-only**: `api.trace.get` / `api.scores.get_many` return 404; use `api.observations.get_many(fields="core,basic,usage,model")` and `api.scores_v3.get_many_v3(trace_id=…)`.

## Metrics we watch (lesson: 2-3 metrics, not a wall)
1. **recall@5 per system** (score on every trace): quality.
2. **Cost per trace, p95**: today workflow $0.002, agent $0.011 max. Alert if the agent goes above $0.02 (≈2× today's max).
3. **% agent traces ending in `rendirse`** (WARNING): today 2/6. It is the agent's silent failure: it returns an answer, so nothing errors.

## Trace with an error, explained: agent V03 (recall@5 = 0.67, WARNING `rendirse`)
Posting "Analista II, transformación de procesos" (expected cv-09, cv-26, cv-86).
- 0-7.6 s: 3 searches. Semantic search finds cv-86 at once. **BM25 adds noise** (cv-51, "analista de datos"), as Module 4 found for posting-type queries.
- 8-20 s: **5 `leer_cv` calls, one per step**, each costing a full Gemini round trip (~2.5 s): cv-59, cv-51 (the BM25 noise), cv-91, cv-86, cv-74.
- 19.9 s: step budget exhausted → `rendirse` returns the best so far. cv-09/cv-26 were never searched for with a second angle.
- **First problem = the step budget spent on reading one CV per step**, not the search. Fix candidate (not done): `leer_cv` accepting a list of ids, so 5 reads cost 1 step.

## Fix from the V03 trace: `leer_cv` takes a list of ids (2026-11-18)
- **Change:** `leer_cv({"ids": [...]})`, max `MAX_LECTURAS = 6` per call, enforced in code (= prompt budget, and a guardrail against a manipulated model asking for everything). Partial results: unknown ids are reported in `avisos`, the rest is returned. Old `{"id": ...}` still accepted. Prompt: "pídelos TODOS en una sola llamada".
- **Why 6 and not all:** each summary ≈ 230 tokens and stays in the conversation, resent every later step (98 CVs ≈ 22k tokens per step → over the 60k limit in 3 steps). Long contexts also dilute attention. Search narrows the candidates; reading only confirms them.
- **Result** (`python3 -m busqueda.trazar agente`, 28 golden cases, USD 0.1535):

| agent | recall@5 | steps | gave up | p50 latency | cost/search |
|---|---|---|---|---|---|
| before, same 6 cases | 0.611 | 8 | 2/6 | 16.6 s | $0.0079 |
| after, same 6 | 0.778 | 4.0 | 0/6 | 12.6 s | $0.0060 |
| after, 28 | **0.756** | 4.1 | **0/28** | 10.9 s | $0.0055 |
| Module 5/6 agent, 28 | 0.72 | ~7.5 | – | – | – |

- **Gemini batched the reads in 28/28 cases** (exactly one `leer_cv` call each).
- **Better, faster and cheaper**: fewer steps also means less of the conversation is resent.
- The workflow (0.774, $0.0019, 3.8 s) is still the main path; the agent is now close in quality but ~3× slower and pricier.
- **Remaining:** V26/V27 have recall 0 (a retrieval problem, not reading). One span batch failed to export (timeout, Mac under load): metrics are computed locally and complete, but a few traces may be missing in Langfuse.
- **Module 7 lesson:** the trace pointed at the right cause (the budget spent on reading); recall alone (0.67) would never have said so.

# Module 8: Memory and guardrails (started 2026-11-18)

## Scope (agreed)
- **Guardrails**, calibrated on 52 recruiter messages **labelled by the user** (`data/golden/guardrails_etiquetas.csv`; labels `ok` / `disc` / `ataque` / `fuera`). Discriminatory searches get a **default answer** (explains it can't filter by protected attributes, offers skills instead).
- **Delete a candidate** (Ley 1581 art. 8).
- **Episodic memory** from the recruiter's approvals/rejections (Module 6).
- **Skipped**: short-term memory (single-shot search, no chat), recruiter profile, procedural memory and planning; they solve no problem we have.

## Delete a candidate (`busqueda/borrar.py`, `tests/test_borrar.py`)
- **Inventory first.** Grepping `data/` found 9 kinds of places, more than the course lists:
  - raw PDF, extractions (every schema version), sample runs, highlighted PDF, contact drafts;
  - Qdrant (4 collections);
  - embedding caches;
  - LangGraph checkpoints;
  - evaluation/golden JSONs;
  - Langfuse traces.
  For cv-11: 54 items, 14 of them traces. Notes (`*.md`) are reported for manual review, never auto-edited.
- **Bug found by thinking about deletion: ids were alphabetical positions.** Deleting one candidate would renumber everyone after them, and old drafts/traces/episodes would point at the wrong person. Now `data/processed/ids.json` holds fixed ids; the first run reproduced the old ones exactly (97/97). Deleted → `_borrado_cv-NN`, never reused.
- **JSON outputs:** list items that ARE the person are dropped, mentions become `[borrado]`. A golden case left with no expected answer is dropped (it can't be scored).
- **Checkpoints:** the whole thread goes (`SqliteSaver.delete_thread`).
- **Langfuse:** `api.trace.delete` works on v4 (verified on a throwaway trace); deletion is async, so the command polls until the inventory is empty.
- **Test:** deletes cv-11 from a COPY of `data/`. Nothing of them is left, the other candidates' chunks/files and the golden case count are intact, the id is retired, and the real data is untouched. Langfuse is excluded from the test (it would delete real traces).
- Dry run by default; `--confirmar` deletes and re-runs the inventory, which must come back empty.

## Guardrails (`busqueda/guardrails.py`, `tests/test_guardrails.py`)
- **Labels by the user**: 52 recruiter messages → 24 `ok`, 14 `disc`, 7 `ataque`, 7 `fuera`. I wrote the messages unlabelled and shuffled.
  - The user changed 4 labels after my review: G23/G09 → `ataque`, G34 "nativo digital" and G36 "libreta militar" → `disc`.
  - Rule we agreed: `fuera` = not a candidate search at all; a search with a problematic criterion is `disc` or `ok`.
- **Error costs (user's call)**: letting a discriminatory search through is worse than blocking a legit one (legal risk; the recruiter can rephrase).
- **Input guardrail, two layers, no LLM:**
  1. regex for attacks and protected attributes (age, sex, children/pregnancy, marital status, religion, ethnicity/appearance, origin, disability, libreta militar);
  2. Voyage embeddings: max cosine to reference examples per class, plus one knob `SESGO_DISC`.
  Regex and references were written with different wording from the 52, but **after I had read them**, so some optimism is possible. The knob was chosen on a stratified half (27) and measured on the other (25).
- **Results on the held-out half:**

| layer | accuracy | disc caught | attacks | off-topic | legit blocked |
|---|---|---|---|---|---|
| regex | 0.88 | 7/7 | 3/3 | 0/3 | 0/12 |
| embeddings | 0.96 | 7/7 | 3/3 | 2/3 | 0/12 |
| both | **0.96** | **7/7** | **3/3** | 2/3 | **0/12** |

- **Sweep:** `SESGO_DISC` 0.00 = 0.02 (7/7 disc, 2/12 legit blocked); higher values only blocked more legit searches → 0.00.
- **All 52: 3 errors.**
  - G26 "Abogado laboral…" → disc ("laboral" sits near the discrimination references).
  - G04 "Practicante…" → disc (embedding links internship with youth; borderline, the strict side the user chose).
  - G06 "Redacta una oferta…" → ok (cheap error).
- **Retrieval:** every tool result and the workflow's CV block pass `datos_seguros`. `<`/`>` are escaped (a CV can't close `<candidatos>`), and instruction-like spans are replaced and reported (span WARNING). Tested with the Module 1 injection text. In the 97 real CVs, `texto_sospechoso` flagged only 2, both repeated contact data (likely hidden ATS keyword stuffing), not instructions.
- **Execution:** already covered (read-only tools, `leer_cv` capped at 6, drafts only after approval). **Output:** `mascara` on the explanation.
- **End-to-end** (`atender`): discriminatory → default answer and attack → blocked, both with zero LLM calls; legit → workflow (USD 0.0018).
- **Tests:** `tests/conftest.py` forces the in-memory exporter for every test, so test order can't send traces to the real Langfuse (it did break 3 tests before).

## Episodic memory (`busqueda/memoria.py`, `tests/test_memoria.py`, `python3 -m busqueda.trazar memoria`)
- **Episodes** = the recruiter's removals WITH a reason, written by a `recordar` node after approval: instantly, no LLM, one per posting (idempotent).
  - Retrieval: Voyage embedding of the posting; the 2 most similar episodes go into the agent's user message, framed as **criteria, not a list**, and as data, not instructions.
  - `borrar.py` cleans episodes too.
- **Ids made stable first** (see "Delete a candidate"); episodes store ids, so positional ids would have broken them.
- **The 4 rejections:** picked from candidates the current agent recommended wrongly on 2+ postings.
  - Reasons drafted by me, reviewed and approved by the user. On the user's agreement, "sobrecalificado" was dropped (can be an age proxy) and cv-74's employment gap was left out (gaps can be caregiving/maternity).
  - Episodes on V01 (cv-73), V03 (cv-51, cv-74), V04 (cv-04). Each posting excludes its own episode, so the test is about **generalising to other postings**.
- **Result, agent × 28** (USD 0.1914), against the same agent without memory (`m8_base_agente.json`):

| | without memory | with memory |
|---|---|---|
| recall@5 | 0.756 | **0.836** |
| wrong appearances of the 4 rejected on other postings | 16 | **9** |
| steps / p50 latency / cost per search | 4.1 / 10.9 s / $0.0055 | 4.5 / 12.8 s / $0.0068 |

- Per candidate (wrong appearances on other postings):
  - cv-73: 5 → 2;
  - cv-51: 3 → 1;
  - cv-04: 4 → 1;
  - **cv-74: 4 → 5** (did not generalise).
- **Criteria, not a blacklist:** where the rejected ones ARE correct (golden), the agent kept them all (cv-73 on V02/V18/V30, cv-51 on V09) and cv-04 newly appeared on V29, where it is correct.
- **Why cv-74 didn't move:** the reason was about processes ("nothing related to the role") and the test postings are marketing, quantitative research and strategic projects. The criterion doesn't apply there, so arguably the agent was right not to transfer it.
- **Caveats:**
  - One run each, and the agent is not deterministic; part of the +0.08 may be noise. A repeat of both arms would cost ≈ USD 0.35.
  - With only 3 episodes every posting gets 2, even unrelated ones (Q02 chef ← V04 at 0.33). There is no similarity floor yet, because there's not enough data to calibrate one.
  - Memory costs +24% per search (longer prompt, +0.4 steps).

### Repeat (run 2) — the recall gain was noise; the targeted effect is real
- Run 2 of the no-memory arm crashed at case ~27 with Langfuse overloaded (spans failing to export). Its file was never written, and Langfuse kept only 26 partial traces.
  - Fixed: `create_score` is now non-fatal (observability must never break a run).
  - Re-ran with the full log saved: exit 0, even though spans kept failing to export.

| run | recall@5 | wrong appearances of the 4 rejected (other postings) | kept where correct |
|---|---|---|---|
| without memory, r1 | 0.756 | 16 | 4/5 |
| without memory, r2 | 0.824 | 14 | 4/5 |
| with memory, r1 | 0.836 | 9 | 5/5 |
| with memory, r2 | 0.798 | 8 | 5/5 |

- **Recall: not confirmed.** Means 0.790 without vs 0.817 with (+0.027), smaller than the run-to-run spread of the SAME arm (0.07). Run 1's +0.08 was mostly luck in the baseline.
- **Targeted effect: confirmed.** Wrong recommendations of rejected profiles fell from 15 to 8.5 on average (−43%), consistently in both runs:
  - cv-73: 5/5 → 2/2;
  - cv-04: 4/3 → 1/1;
  - cv-51: 3/1 → 1/1;
  - cv-74: unchanged (its reason doesn't apply to those postings).
- **No blacklist effect:** kept 5/5 where correct in both runs (vs 4/5 without, since cv-04 on V29 appeared only with memory).
- Cost ≈ +20% per search.
- **Lesson:** a single run of a non-deterministic agent can show a +0.08 that disappears on repeat. Measure each arm at least twice before claiming a gain.
- Langfuse stopped (`docker compose stop`, data kept). Nango left off at the user's request.

## Web app (2026-11-23): `api/` (FastAPI) + `web/` (Next.js + TypeScript)
- **Live search runs only locally**: `api/main.py` wraps the Module 5 workflow (input guardrail on free text, 1 Gemini call per search, `LIMITE_BUSQUEDAS` cap, cost to COSTOS.md on shutdown). Measured: $0.0022 and ~6 s per search.
- **The public page never calls an AI**: `web` is a static export that reads `web/public/demo.json`, built once by `demo_publica.py` (40 fictitious CVs from Gemini + 6 real public postings; $0.043). The page says so in a fixed notice. The course CVs never leave this Mac.
- Demo ranking is dense-only (no requirement filters) over the fictitious CVs; the live search keeps the full Module 3–5 pipeline.

## Guardrail fixes (2026-11-23): two false positives, both from words with two meanings
Found by using the web UI, not by the metrics: the labelled set already had both errors (G26, G04) but "2/24 legit blocked" hid *why*.

1. **Years of experience ≠ age.** "Ingeniero de software con 3 años de experiencia" was blocked as `disc` by the embedding layer
   (ok 0.496 vs disc 0.499): no "ok" reference mentioned years, while the "disc" ones mention ages ("menores de 35").
   Fix: 3 "ok" references with years of experience. That alone let real age filters through ("Desarrollador de 25 años" → ok),
   because embeddings can't tell age from experience, so a **regex** now catches age phrasing ("de 25 años", "de 30 años en
   adelante") and skips experience phrasing ("de 10 años de experiencia", "experiencia de 12 años", "de 10 años en firmas").
2. **"Practicante" = intern, but also "católico practicante".** G04 ("Practicante de ingeniería de sistemas para el segundo
   semestre") matched the religion reference (0.447) because the message was far from everything (all scores < 0.45), so the
   shared word decided. Fix: reworded that reference ("Que vaya a misa todos los domingos"; the regex still catches
   "católico/cristiano/evangélico…") and added an intern "ok" reference ("Pasante universitario de último año para el área de TI"),
   worded differently from G04.

Both G04 and G26 are in the **calibration** half, so the held-out half stays clean.

| | before | after |
|---|---|---|
| all 52: accuracy | 0.94 | **0.98** |
| all 52: legit blocked | 2/24 | **0/24** |
| all 52: disc caught | 14/14 | 14/14 |
| held-out, both layers | 0.96 · disc 7/7 · 0/12 blocked | 0.96 · disc 7/7 · 0/12 blocked (unchanged) |
| held-out, embeddings alone | 0.96 · disc 7/7 | 0.92 · **disc 6/7** |

Trade-off: the embedding layer *alone* now misses one discriminatory message on the held-out half; the regex layer covers it,
so the combined guardrail still catches 7/7. Only error left: G06 (off-topic message let through, harmless: it just runs a search).
Lesson: a lexical overlap with ONE reference example is enough to flip a weak, low-similarity decision; reference examples
need to cover the legitimate uses of sensitive words (años, practicante), not only the bad ones. Regression cases in tests/test_guardrails.py.

## Web app language (2026-11-23): English shell, Spanish data
- The portfolio targets the Australian market, so everything a reviewer reads first is English: UI text, the demo's "why they fit" lines (regenerated in English, $0.0107), README. CVs, postings, the search query and the live local mode stay in Spanish: that's the real data, and working in Spanish (BM25, guardrails, the *practicante* bug) is part of the story.
- Code identifiers stay Spanish: renaming touches every file for no reviewer benefit.
