import { createContext, useContext } from "react";
import type { Api, Job, JobChanges } from "./api";

export interface AppCtx {
  api: Api;
  /** latest version of each job changed in this session, by id */
  changed: Record<number, Job>;
  open: (job: Job) => void;
  change: (job: Job, changes: JobChanges) => Promise<Job | null>;
  toast: (text: string) => void;
  /** ids newer than this are "new" (Novedades) */
  seenId: number;
  /** reload every list (the profile changed every job's compatibility) */
  refreshAll: () => void;
}

export const Ctx = createContext<AppCtx | null>(null);

export function useApp(): AppCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp outside the app");
  return ctx;
}
