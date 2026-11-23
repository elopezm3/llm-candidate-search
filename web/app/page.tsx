"use client";

import { useEffect, useState } from "react";

// Set → live search against the local FastAPI (your keys, real CVs). Unset → static demo from /demo.json, no AI at all.
const API = process.env.NEXT_PUBLIC_API_URL;

type Candidato = {
  id: string;
  nombre: string;
  ciudad?: string;
  anos_experiencia: number | null;
  experiencia: string[];
  educacion: string[];
  tecnologias: string[];
  idiomas: string[];
  motivo: string | null;
};
type Resultado = { cargo?: string; consulta: string; candidatos: Candidato[]; usd?: number; usd_sesion?: number };
type Demo = { generado: string; total_cvs: number; busquedas: Resultado[] };
type Vacante = { archivo: string; cargo: string };

export default function Page() {
  return (
    <main>
      <header className="cabecera">
        <h1>AI candidate search</h1>
        <p className="sub">
          Pick a job posting and the system ranks the CVs by fit, with one line on why each person fits or what they are missing.
        </p>
        <p className="dataset">
          Dataset: Spanish-language CVs and job postings from Colombia. Retrieval, keyword search and guardrails all work in
          Spanish; the explanations are written in English.
        </p>
      </header>
      {API ? <EnVivo /> : <DemoEstatica />}
      <footer>
        <a href="https://github.com/elopezm3/llm-candidate-search">Code, metrics and design decisions on GitHub</a>
      </footer>
    </main>
  );
}

function DemoEstatica() {
  const [demo, setDemo] = useState<Demo | null>(null);
  const [error, setError] = useState(false);
  const [i, setI] = useState(0);

  useEffect(() => {
    fetch("demo.json")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setDemo)
      .catch(() => setError(true));
  }, []);

  return (
    <>
      <aside className="aviso" role="note" aria-label="How this demo works">
        <strong>Pre-computed demo: this page does not run AI live.</strong>
        <ul>
          <li>
            The results were generated <b>once</b>, locally, over <b>{demo?.total_cvs ?? 40} fictitious CVs</b> created for
            this demo. None of these people are real.
          </li>
          <li>
            <b>Why? Budget.</b> Every live search pays for AI model calls, and a public page could run up costs with no limit.
            So this page is static: it calls no model and no API, and using it <b>costs nothing</b>.
          </li>
          <li>
            The live search (free text, guardrails, hybrid search and requirement filters) runs only locally; see the README.
            The job postings are real public ads.
          </li>
        </ul>
        {demo && <p className="fecha">Generated on {demo.generado}.</p>}
      </aside>

      {error && <p className="error">Could not load demo.json.</p>}
      {demo && (
        <>
          <h2 className="etiqueta">Job posting</h2>
          <div className="vacantes" role="tablist" aria-label="Example job postings">
            {demo.busquedas.map((b, j) => (
              <button key={b.cargo} lang="es" role="tab" aria-selected={i === j} className="chip" onClick={() => setI(j)}>
                {b.cargo}
              </button>
            ))}
          </div>
          <Resultados r={demo.busquedas[i]} />
        </>
      )}
    </>
  );
}

function EnVivo() {
  const [vacantes, setVacantes] = useState<Vacante[]>([]);
  const [vacante, setVacante] = useState("");
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const [r, setR] = useState<Resultado | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/vacantes`)
      .then((x) => x.json())
      .then(setVacantes)
      .catch(() => setMensaje("The API is not responding. Is `npm run api` running?"));
  }, []);

  async function buscar(cuerpo: { vacante?: string; consulta?: string }) {
    setCargando(true);
    setMensaje(null);
    setR(null);
    try {
      const res = await fetch(`${API}/buscar`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(cuerpo),
      });
      const d = await res.json();
      if (!res.ok) setMensaje(typeof d.detail === "string" ? d.detail : "The search failed.");
      else if (d.bloqueado) setMensaje(d.respuesta);
      else setR(d);
    } catch {
      setMensaje("The API is not responding.");
    } finally {
      setCargando(false);
    }
  }

  return (
    <>
      <aside className="aviso vivo" role="note">
        <strong>Live local mode.</strong> Each search calls Gemini with your keys (≈ US$0.002) over the real CVs. There is a
        per-session search cap and the spend is logged in COSTOS.md.
      </aside>

      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          buscar(vacante ? { vacante } : { consulta: texto });
        }}
      >
        <label htmlFor="vacante">Job posting</label>
        <select id="vacante" value={vacante} onChange={(e) => setVacante(e.target.value)}>
          <option value="">Free text…</option>
          {vacantes.map((v) => (
            <option key={v.archivo} value={v.archivo}>
              {v.cargo}
            </option>
          ))}
        </select>
        {!vacante && (
          <>
            <label htmlFor="texto">Profile you are looking for (in Spanish)</label>
            <textarea
              id="texto"
              rows={3}
              maxLength={500}
              placeholder="E.g.: ingeniero de datos con Airflow y Spark, inglés B2"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
            />
          </>
        )}
        <button className="primario" disabled={cargando || (!vacante && !texto.trim())}>
          {cargando ? "Searching…" : "Search"}
        </button>
      </form>

      {mensaje && (
        <p className="error" role="alert">
          {mensaje}
        </p>
      )}
      {r && (
        <>
          <Resultados r={r} />
          <p className="fecha">
            This search: US${r.usd?.toFixed(4)} · session: US${r.usd_sesion?.toFixed(4)}
          </p>
        </>
      )}
    </>
  );
}

function Resultados({ r }: { r: Resultado }) {
  return (
    <section aria-live="polite">
      <details className="consulta">
        <summary>Search query built from the posting</summary>
        <p lang="es">{r.consulta}</p>
      </details>
      <ol className="lista">
        {r.candidatos.map((c, n) => (
          <li key={c.id} className="tarjeta">
            <div className="fila">
              <span className="puesto" aria-hidden>
                {n + 1}
              </span>
              <div className="quien">
                <h3>{c.nombre}</h3>
                <p className="meta">
                  <span lang="es">{c.experiencia[0]?.split(" (")[0] ?? "—"}</span>
                  {" · "}
                  {c.anos_experiencia ?? "?"} yrs{c.ciudad ? ` · ${c.ciudad}` : ""}
                </p>
              </div>
              <code className="id">{c.id}</code>
            </div>
            {c.motivo && <p className="motivo">{c.motivo}</p>}
            <ul className="tags" aria-label="Technologies">
              {c.tecnologias.slice(0, 8).map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            <details>
              <summary>Show summary</summary>
              <div lang="es">
                <h4>Experience</h4>
                <ul>{c.experiencia.map((e) => <li key={e}>{e}</li>)}</ul>
                <h4>Education</h4>
                <ul>{c.educacion.map((e) => <li key={e}>{e}</li>)}</ul>
                <h4>Languages</h4>
                <p>{c.idiomas.join(" · ")}</p>
              </div>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}
