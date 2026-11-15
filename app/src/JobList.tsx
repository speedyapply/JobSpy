import { useEffect, useRef } from "react";
import { belongs, type Filters, type ListName } from "./api";
import { useApp } from "./context";
import { useJobList } from "./hooks";
import { JobCard } from "./JobCard";

/** A list of job cards from the server, with paging; jobs changed elsewhere in the
 *  app show their new state, and leave the list when they no longer belong */
export function JobList({
  list,
  filters = {},
  empty,
  pageSize = 20,
  limit,
  reloadKey = 0,
  onTotal,
}: {
  list: ListName;
  filters?: Filters;
  empty: string;
  pageSize?: number;
  /** show at most this many, without "load more" (home sections) */
  limit?: number;
  reloadKey?: number;
  onTotal?: (total: number) => void;
}) {
  const { api, changed, seenId } = useApp();
  const { jobs, total, loading, error, reload, more, drop } = useJobList(api, list, filters, limit ?? pageSize, reloadKey);

  // a job changed elsewhere that doesn't belong here any more
  useEffect(() => {
    for (const job of jobs) {
      const latest = changed[job.id];
      if (latest && !belongs(latest, list)) drop(job.id);
    }
  }, [changed, jobs, list, drop]);

  // a job changed elsewhere that now belongs here (saved from Inicio, say): reload
  const jobsRef = useRef(jobs);
  jobsRef.current = jobs;
  const seenChanges = useRef(changed);
  useEffect(() => {
    const previous = seenChanges.current;
    seenChanges.current = changed;
    if (previous === changed || list === "recent" || list === "all" || limit) return;
    const arrived = Object.values(changed).some(
      (job) => previous[job.id] !== job && belongs(job, list) && !jobsRef.current.some((j) => j.id === job.id),
    );
    if (arrived) void reload();
  }, [changed, list, limit, reload]);

  useEffect(() => onTotal?.(total), [total, onTotal]);

  const shown = jobs.map((j) => changed[j.id] ?? j);
  return (
    <div className="job-list">
      {error && (
        <div className="error-box">
          <p>{error}</p>
          <button onClick={() => void reload()}>Reintentar</button>
        </div>
      )}
      {loading && !jobs.length && !error && <div className="skeleton" aria-label="Cargando" />}
      {!loading && !error && !jobs.length && <p className="empty">{empty}</p>}
      {shown.map((job) => (
        <JobCard key={job.id} job={job} isNew={job.id > seenId} />
      ))}
      {!limit && jobs.length < total && !error && (
        <button className="wide" disabled={loading} onClick={() => void more()}>
          {loading ? "Cargando…" : `Ver más (${total - jobs.length})`}
        </button>
      )}
    </div>
  );
}
