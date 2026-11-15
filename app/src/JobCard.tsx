import type { Job } from "./api";
import { useApp } from "./context";
import { ago, place, salary, scoreClass } from "./format";
import { StarIcon } from "./icons";

export function Score({ job, large = false }: { job: Job; large?: boolean }) {
  if (job.match == null) return null;
  return (
    <span className={`${scoreClass(job.match)}${large ? " large" : ""}`} title={job.match_detail.title_only ? "Solo por el título" : undefined}>
      {job.match}%{job.match_detail.title_only ? "*" : ""}
    </span>
  );
}

export function Skills({ job, max = 6 }: { job: Job; max?: number }) {
  const { have, missing, warnings } = job.match_detail;
  if (!have.length && !missing.length && !warnings.length) return null;
  return (
    <div className="chips">
      {have.slice(0, max).map((s) => (
        <span key={`h${s}`} className="chip have">
          {s}
        </span>
      ))}
      {missing.slice(0, max).map((s) => (
        <span key={`m${s}`} className="chip missing">
          {s}
        </span>
      ))}
      {warnings.map((w) => (
        <span key={`w${w}`} className="chip warning">
          {w}
        </span>
      ))}
    </div>
  );
}

export function SaveButton({ job }: { job: Job }) {
  const { change } = useApp();
  return (
    <button
      className={job.saved_at ? "star on" : "star"}
      aria-label={job.saved_at ? "Quitar de guardadas" : "Guardar"}
      onClick={(e) => {
        e.stopPropagation();
        void change(job, { saved: !job.saved_at });
      }}
    >
      <StarIcon filled={Boolean(job.saved_at)} />
    </button>
  );
}

export function JobCard({ job, isNew = false }: { job: Job; isNew?: boolean }) {
  const { open, change } = useApp();
  const pay = salary(job.salary);
  const posted = ago(job.date_posted) ?? ago(job.first_seen);
  return (
    <article className="card" onClick={() => open(job)}>
      <div className="card-top">
        <div className="card-titles">
          {isNew && <span className="new-badge">Nueva</span>}
          <h3>{job.title}</h3>
          {job.company && <div className="company">{job.company}</div>}
        </div>
        <SaveButton job={job} />
      </div>
      <div className="meta">
        {place(job) && <span>{place(job)}</span>}
        {pay && <span className="pay">{pay}</span>}
      </div>
      <Skills job={job} max={4} />
      {job.note && <div className="note">📝 {job.note}</div>}
      <div className="card-bottom">
        <Score job={job} />
        <span className="muted small">
          {posted}
          {job.site ? ` · ${job.site}` : ""}
        </span>
        <span className="spacer" />
        {job.applied_at ? (
          <span className="tag applied">Aplicada</span>
        ) : (
          <button
            className="text-btn"
            onClick={(e) => {
              e.stopPropagation();
              void change(job, { hidden: !job.hidden_at });
            }}
          >
            {job.hidden_at ? "Recuperar" : "Descartar"}
          </button>
        )}
      </div>
    </article>
  );
}
