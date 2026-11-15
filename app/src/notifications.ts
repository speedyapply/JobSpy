// Notifications for new jobs. The server has no push service: the phone asks it
// (GET /api/updates?after=<last id seen>) when the app opens or comes back, every few
// minutes while it is open, and every 15 minutes in the background through
// @capacitor/background-runner (public/runners/background.js). The last job id
// notified is shared with that runner so a job is announced once.

import type { Api, Job, ServerConfig } from "./api";

export interface NotifySettings {
  enabled: boolean;
  minMatch: number;
  lastId: number; // newest job id already announced
}

const KEY = "radar.notify";
const RUNNER = "es.mansour.radarofertas.check";
const DEFAULTS: NotifySettings = { enabled: false, minMatch: 0, lastId: 0 };

export function loadNotify(): NotifySettings {
  try {
    return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<NotifySettings>) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveNotify(settings: NotifySettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    // storage unavailable: settings last this session
  }
}

function isNative(): boolean {
  const cap = (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
  return Boolean(cap?.isNativePlatform?.());
}

export type Permission = "granted" | "denied" | "prompt" | "unsupported";

export async function permission(): Promise<Permission> {
  if (isNative()) {
    try {
      const { LocalNotifications } = await import("@capacitor/local-notifications");
      const { display } = await LocalNotifications.checkPermissions();
      return display === "granted" ? "granted" : display === "denied" ? "denied" : "prompt";
    } catch {
      return "unsupported";
    }
  }
  if (!("Notification" in window)) return "unsupported";
  return Notification.permission === "default" ? "prompt" : (Notification.permission as Permission);
}

/** Asks Android (13+) or the browser for permission to notify */
export async function requestPermission(): Promise<Permission> {
  if (isNative()) {
    try {
      const { LocalNotifications } = await import("@capacitor/local-notifications");
      const { display } = await LocalNotifications.requestPermissions();
      try {
        const { BackgroundRunner } = await import("@capacitor/background-runner");
        await BackgroundRunner.requestPermissions({ apis: ["notifications"] });
      } catch {
        // the background runner is optional: foreground checks still work
      }
      return display === "granted" ? "granted" : "denied";
    } catch {
      return "unsupported";
    }
  }
  if (!("Notification" in window)) return "unsupported";
  const result = await Notification.requestPermission();
  return result === "default" ? "prompt" : (result as Permission);
}

function pct(job: Job): string {
  return job.match == null ? "" : `${job.match}% · `;
}

/** One notification: the job itself if it is one, a summary if several */
export function message(jobs: Job[], total: number): { title: string; body: string; jobId: number | null } {
  if (total === 1 && jobs[0]) {
    const job = jobs[0];
    return {
      title: `${pct(job)}${job.title}`,
      body: [job.company, job.location].filter(Boolean).join(" · ") || "Nueva oferta",
      jobId: job.id,
    };
  }
  const best = jobs.slice(0, 3).map((j) => `${pct(j)}${j.title}`);
  return { title: `${total} ofertas nuevas`, body: best.join("\n"), jobId: null };
}

async function show(title: string, body: string, jobId: number | null): Promise<void> {
  if (isNative()) {
    const { LocalNotifications } = await import("@capacitor/local-notifications");
    await LocalNotifications.schedule({
      notifications: [
        {
          id: Math.floor(Date.now() % 2147483647),
          title,
          body,
          largeBody: body,
          extra: { jobId },
        },
      ],
    });
    return;
  }
  if ("Notification" in window && Notification.permission === "granted") {
    const n = new Notification(title, { body, tag: "radar-ofertas" });
    n.onclick = () => {
      window.focus();
      window.dispatchEvent(new CustomEvent("radar:open", { detail: { jobId } }));
    };
  }
}

/**
 * Asks the server for jobs newer than the last one announced and notifies them.
 * The first time it only remembers the newest id, so old jobs don't flood in.
 * Returns how many new jobs it announced.
 */
let checking: Promise<number> | null = null;

export function check(api: Api, config: ServerConfig): Promise<number> {
  // one check at a time: opening the app and the timer can ask at once
  checking ??= checkNow(api, config).finally(() => {
    checking = null;
  });
  return checking;
}

async function checkNow(api: Api, config: ServerConfig): Promise<number> {
  const settings = loadNotify();
  if (!settings.enabled) return 0;
  const after = Math.max(settings.lastId, await runnerLastId());
  const updates = await api.updates(after, settings.minMatch, 3);
  const next = { ...settings, lastId: Math.max(after, updates.newest_id) };
  saveNotify(next);
  await syncRunner(config, next);
  if (after === 0 || updates.total === 0) return 0;
  const { title, body, jobId } = message(updates.jobs, updates.total);
  await show(title, body, jobId);
  return updates.total;
}

/** A test notification, from the profile screen */
export async function test(): Promise<void> {
  await show("Notificaciones activadas", "Te avisaré cuando el servidor encuentre ofertas nuevas.", null);
}

/** Hands the server, token and threshold to the background runner */
export async function syncRunner(config: ServerConfig | null, settings: NotifySettings): Promise<void> {
  if (!isNative()) return;
  try {
    const { BackgroundRunner } = await import("@capacitor/background-runner");
    await BackgroundRunner.dispatchEvent({
      label: RUNNER,
      event: "configure",
      details: {
        url: config?.url ?? "",
        token: config?.token ?? "",
        enabled: settings.enabled && Boolean(config?.url),
        minMatch: settings.minMatch,
        lastId: settings.lastId,
      },
    });
  } catch {
    // no runner (web, or plugin missing): only foreground checks
  }
}

/** The newest id the background runner announced, to not repeat it */
async function runnerLastId(): Promise<number> {
  if (!isNative()) return 0;
  try {
    const { BackgroundRunner } = await import("@capacitor/background-runner");
    const state = (await BackgroundRunner.dispatchEvent({ label: RUNNER, event: "state", details: {} })) as {
      lastId?: number | string;
    } | null;
    return Number(state?.lastId ?? 0) || 0;
  } catch {
    return 0;
  }
}

/** Tapping a notification: open that job, or the Novedades tab */
export async function onTap(handler: (jobId: number | null) => void): Promise<() => void> {
  const web = (e: Event) => handler((e as CustomEvent<{ jobId: number | null }>).detail.jobId);
  window.addEventListener("radar:open", web);
  let remove = () => window.removeEventListener("radar:open", web);
  if (isNative()) {
    try {
      const { LocalNotifications } = await import("@capacitor/local-notifications");
      const listener = await LocalNotifications.addListener("localNotificationActionPerformed", (action) => {
        const id = Number((action.notification.extra as { jobId?: number } | undefined)?.jobId);
        handler(Number.isFinite(id) && id > 0 ? id : null);
      });
      const previous = remove;
      remove = () => {
        previous();
        void listener.remove();
      };
    } catch {
      // plugin missing
    }
  }
  return () => remove();
}

/** Calls fn when the app comes back to the foreground */
export async function onResume(fn: () => void): Promise<() => void> {
  const visible = () => document.visibilityState === "visible" && fn();
  document.addEventListener("visibilitychange", visible);
  let remove = () => document.removeEventListener("visibilitychange", visible);
  if (isNative()) {
    try {
      const { App } = await import("@capacitor/app");
      const listener = await App.addListener("resume", fn);
      const previous = remove;
      remove = () => {
        previous();
        void listener.remove();
      };
    } catch {
      // plugin missing
    }
  }
  return () => remove();
}
