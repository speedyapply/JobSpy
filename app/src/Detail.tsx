import { useEffect, useState } from "react";
import type { Job } from "./api";
import { useApp } from "./context";
import { ago, place, salary, shortDate } from "./format";
import { BackIcon, ExternalIcon } from "./icons";
import { SaveButton, Score, Skills } from "./JobCard";
import { openExternal } from "./platform";

/** Descriptions come as markdown with a blank line after every line: tighten them */
function tidy(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/\\([<>*_#\-+.!\[\]()`])/g, "$1")
    .replace(/\n[ \t]*\n(?=[^\n])/g, "\n")
    .trim();
}

export function Detail({ job: summary, onBack }: { job: Job; onBack: () => void }) {
  const { api, change, changed } = useApp();
  const [full, setFull] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState(summary.note ?? "");
  const [savingNote, setSavingNote] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .job(summary.id)
      .then((j) => {
        if (!alive) return;
        setFull(j);
        setNote(j.note ?? "");
      })
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [api, summary.id]);

  // the freshest state: a change made here or elsewhere, over what the server sent
  const job: Job = { ...summary, ...(full ?? {}), ...(changed[summary.id] ?? {}), description: full?.description };

  const saveNote = async () => {
    setSavingNote(true);
    await change(job, { note: note.trim() || null });
    setSavingNote(false);
  };

  const pay = salary(job.salary);
  const posted = ago(job.date_posted);
  return (
    <div className="page detail">
      <header className="top-bar">
        <button className="icon-btn" onClick={onBack} aria-label="Volver">
          <BackIcon />
        </button>
        <span className="spacer" />
        <SaveButton job={job} />
        <button className="icon-btn" onClick={() => openExternal(job.job_url)} aria-label="Abrir en la web">
          <ExternalIcon />
        </button>
      </header>
      <div className="page-body">
        <div className="detail-head">
          <div>
            <h1>{job.title}</h1>
            {job.company && <div className="company big">{job.company}</div>}
          </div>
          <Score job={job} large />
        </div>
        <dl className="facts">
          {place(job) && (
            <>
              <dt>Dónde</dt>
              <dd>{place(job)}</dd>
            </>
          )}
          {pay && (
            <>
              <dt>Salario</dt>
              <dd className="pay">{pay}</dd>
            </>
          )}
          {posted && (
            <>
              <dt>Publicada</dt>
              <dd>
                {posted} {shortDate(job.date_posted) ? `(${shortDate(job.date_posted)})` : ""}
              </dd>
            </>
          )}
          {job.job_type && (
            <>
              <dt>Tipo</dt>
              <dd>{job.job_type}</dd>
            </>
          )}
          <dt>Fuente</dt>
          <dd>
            {job.site ?? "—"}
            {job.search ? ` · «${job.search}»` : ""}
          </dd>
        </dl>

        <div className="detail-actions">
          <button className={job.applied_at ? "on" : ""} onClick={() => void change(job, { applied: !job.applied_at })}>
            {job.applied_at ? `✓ Aplicada ${ago(job.applied_at) ?? ""}` : "Marcar como aplicada"}
          </button>
          <button className={job.hidden_at ? "on" : ""} onClick={() => void change(job, { hidden: !job.hidden_at })}>
            {job.hidden_at ? "Recuperar" : "Descartar"}
          </button>
        </div>

        {job.match != null && (
          <section className="panel">
            <h2>
              Compatibilidad contigo: {job.match}%{job.match_detail.title_only ? " (solo por el título)" : ""}
            </h2>
            <Skills job={job} max={20} />
            <p className="muted small">Verde: lo tienes · rojo: te falta · amarillo: a tener en cuenta.</p>
          </section>
        )}

        <section className="panel">
          <h2>Mis notas</h2>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Ej.: llamar el lunes, pedir rango salarial…"
            rows={3}
            maxLength={2000}
          />
          <button className="primary" disabled={savingNote || note.trim() === (job.note ?? "")} onClick={() => void saveNote()}>
            {savingNote ? "Guardando…" : "Guardar nota"}
          </button>
        </section>

        <section className="panel">
          <h2>Descripción</h2>
          {!full && !error && <p className="muted">Cargando…</p>}
          {error && <p className="error">{error}</p>}
          {full &&
            (full.description ? (
              <div className="description">{tidy(full.description)}</div>
            ) : (
              <p className="muted">Esta oferta no trae descripción. Ábrela en la web.</p>
            ))}
        </section>
      </div>
      <div className="cta">
        <button className="primary" onClick={() => openExternal(job.job_url)}>
          Ver oferta en {job.site ?? "la web"}
        </button>
      </div>
    </div>
  );
}
