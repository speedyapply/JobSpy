import { useCallback, useEffect, useRef, useState } from "react";
import type { Api, Filters, Job, ListName } from "./api";

/** A paged list of jobs from the server, reloaded when the list or filters change */
export function useJobList(api: Api, list: ListName, filters: Filters, pageSize = 20, reloadKey = 0) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);
  const key = JSON.stringify(filters);

  const load = useCallback(
    async (offset: number) => {
      const id = ++request.current;
      setLoading(true);
      setError(null);
      try {
        const page = await api.jobs(list, JSON.parse(key) as Filters, offset, pageSize);
        if (id !== request.current) return; // a newer request won
        setJobs((current) =>
          offset === 0 ? page.jobs : [...current, ...page.jobs.filter((j) => !current.some((c) => c.id === j.id))],
        );
        setTotal(page.total);
      } catch (e) {
        if (id === request.current) setError((e as Error).message);
      } finally {
        if (id === request.current) setLoading(false);
      }
    },
    [api, list, key, pageSize],
  );

  useEffect(() => {
    void load(0);
  }, [load, reloadKey]);

  /** A job left the list (e.g. discarded): drop it without reloading */
  const drop = useCallback((id: number) => {
    setJobs((current) => {
      if (!current.some((j) => j.id === id)) return current;
      setTotal((t) => Math.max(0, t - 1));
      return current.filter((j) => j.id !== id);
    });
  }, []);

  return {
    jobs,
    total,
    loading,
    error,
    reload: useCallback(() => load(0), [load]),
    more: () => load(jobs.length),
    drop,
  };
}

/** A value that settles a moment after the last change, for search-as-you-type */
export function useDebounced<T>(value: T, ms = 400): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return settled;
}
