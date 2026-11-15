// The backend's API (runner/api.py). The server address and token live on the phone.

export type ListName = "recent" | "top" | "saved" | "applied" | "hidden" | "all";

export interface Salary {
  min: number | null;
  max: number | null;
  interval: string | null;
  currency: string | null;
}

export interface Job {
  id: number;
  job_url: string;
  site: string | null;
  search: string | null;
  title: string;
  company: string | null;
  location: string | null;
  date_posted: string | null;
  first_seen: string | null;
  is_remote: boolean;
  work_from_home_type: string | null;
  job_type: string | null;
  salary: Salary | null;
  match: number | null;
  match_detail: { have: string[]; missing: string[]; warnings: string[]; title_only: boolean };
  saved_at: string | null;
  applied_at: string | null;
  hidden_at: string | null;
  note: string | null;
  has_description: boolean;
  description?: string | null;
}

export interface JobPage {
  list: ListName;
  q: string;
  total: number;
  offset: number;
  limit: number;
  jobs: Job[];
}

export interface Stats {
  total: number;
  saved: number;
  applied: number;
  hidden: number;
  week: number;
  good_week: number;
  sites: Record<string, number>;
  last_run: string | null;
  last_run_result: { new: number; errors: string[] } | null;
  next_run: string | null;
  running: boolean;
  interval_hours: number;
}

export interface Search {
  name?: string;
  site_name?: string | string[];
  search_term?: string;
  location?: string;
  is_remote?: boolean;
  hours_old?: number;
}

export interface Health {
  ok: boolean;
  version: string;
  jobs: number;
  running: boolean;
}

export interface Updates {
  after: number;
  newest_id: number;
  total: number;
  jobs: Job[];
}

export interface Profile {
  skills: string[];
  roles: string[];
  years_experience: number;
  locations: string[];
  remote_ok: boolean;
  english: string;
}

export interface CvInfo {
  name: string;
  size: number;
  uploaded_at: string | null;
  skills: string[];
  suggested: string[];
}

export interface Filters {
  q?: string;
  minMatch?: number;
  remote?: boolean;
}

export type JobChanges = Partial<{ saved: boolean; applied: boolean; hidden: boolean; note: string | null }>;

export interface ServerConfig {
  url: string;
  token: string;
}

const KEY = "radar.server";

export function loadConfig(): ServerConfig | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const config = JSON.parse(raw) as ServerConfig;
    return config.url ? config : null;
  } catch {
    return null;
  }
}

export function saveConfig(config: ServerConfig): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(config));
  } catch {
    // private mode or storage full: the config lasts until the app closes
  }
}

/** "mi-pc:8000" -> "http://mi-pc:8000"; trailing slashes off */
export function normaliseUrl(url: string): string {
  let clean = url.trim().replace(/\/+$/, "");
  if (clean && !/^https?:\/\//i.test(clean)) clean = `http://${clean}`;
  return clean;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export class Api {
  constructor(private config: ServerConfig) {}

  private async request<T>(path: string, init: RequestInit = {}, timeoutMs = 15000): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const headers: Record<string, string> = { Accept: "application/json" };
    if (this.config.token) headers.Authorization = `Bearer ${this.config.token}`;
    if (init.body) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch(`${this.config.url}${path}`, { ...init, headers, signal: controller.signal });
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      throw new ApiError(
        aborted
          ? "El servidor no responde. ¿Está encendido y conectado a Tailscale?"
          : "No se pudo conectar con el servidor. Revisa la dirección y que el móvil esté en Tailscale.",
        0,
      );
    } finally {
      clearTimeout(timer);
    }
    if (response.status === 401) throw new ApiError("Token incorrecto o vacío.", 401);
    if (!response.ok) {
      let message = `Error ${response.status}`;
      try {
        const body = (await response.json()) as { error?: string };
        if (body.error) message += `: ${body.error}`;
      } catch {
        // not JSON
      }
      throw new ApiError(message, response.status);
    }
    const type = response.headers.get("content-type") ?? "";
    return (type.includes("json") ? await response.json() : await response.text()) as T;
  }

  health(): Promise<Health> {
    return this.request("/api/health", {}, 8000);
  }

  jobs(list: ListName, filters: Filters, offset: number, limit = 20): Promise<JobPage> {
    const params = new URLSearchParams({ list, offset: String(offset), limit: String(limit) });
    if (filters.q) params.set("q", filters.q);
    if (filters.minMatch) params.set("min_match", String(filters.minMatch));
    if (filters.remote) params.set("remote", "1");
    return this.request(`/api/jobs?${params}`);
  }

  updates(after: number, minMatch = 0, limit = 50): Promise<Updates> {
    const params = new URLSearchParams({ after: String(after), min_match: String(minMatch), limit: String(limit) });
    return this.request(`/api/updates?${params}`);
  }

  profile(): Promise<Profile> {
    return this.request("/api/profile");
  }

  saveProfile(profile: Partial<Profile>): Promise<Profile & { rescored: number }> {
    return this.request("/api/profile", { method: "PUT", body: JSON.stringify(profile) }, 60000);
  }

  async cvInfo(): Promise<CvInfo | null> {
    try {
      return await this.request<CvInfo>("/api/cv/info");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  }

  /** The PDF goes as base64 in JSON: Capacitor's native HTTP carries text reliably */
  uploadCv(name: string, base64: string): Promise<CvInfo> {
    return this.request("/api/cv", { method: "PUT", body: JSON.stringify({ name, data: base64 }) }, 60000);
  }

  cv(): Promise<{ name: string; data: string }> {
    return this.request("/api/cv?format=base64", {}, 60000);
  }

  deleteCv(): Promise<{ deleted: boolean }> {
    return this.request("/api/cv", { method: "DELETE" });
  }

  job(id: number): Promise<Job> {
    return this.request(`/api/jobs/${id}`);
  }

  update(id: number, changes: JobChanges): Promise<Job> {
    return this.request(`/api/jobs/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
  }

  stats(): Promise<Stats> {
    return this.request("/api/stats");
  }

  searches(): Promise<Search[]> {
    return this.request("/api/searches");
  }

  exportCsv(lists = "saved,applied"): Promise<string> {
    return this.request(`/api/export.csv?list=${encodeURIComponent(lists)}`, {}, 30000);
  }
}

/** Whether a job still belongs in a list after a change */
export function belongs(job: Job, list: ListName): boolean {
  switch (list) {
    case "recent":
      return !job.hidden_at;
    case "top":
      return !job.hidden_at && !job.applied_at;
    case "saved":
      return Boolean(job.saved_at);
    case "applied":
      return Boolean(job.applied_at);
    case "hidden":
      return Boolean(job.hidden_at);
    case "all":
      return true;
  }
}
