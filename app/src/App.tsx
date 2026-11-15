import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactElement } from "react";
import { Api, loadConfig, saveConfig, type Job, type JobChanges, type ServerConfig } from "./api";
import { Ctx, type AppCtx } from "./context";
import { Detail } from "./Detail";
import { Home } from "./Home";
import { BellIcon, BriefcaseIcon, HomeIcon, UserIcon } from "./icons";
import { JobsScreen } from "./JobsScreen";
import { News } from "./News";
import * as notifications from "./notifications";
import { onBackButton } from "./platform";
import { ProfileScreen } from "./ProfileScreen";
import { Welcome } from "./Settings";

type Tab = "home" | "jobs" | "news" | "profile";
const TABS: { name: Tab; label: string; Icon: (p: { size?: number }) => ReactElement }[] = [
  { name: "home", label: "Inicio", Icon: HomeIcon },
  { name: "jobs", label: "Empleos", Icon: BriefcaseIcon },
  { name: "news", label: "Novedades", Icon: BellIcon },
  { name: "profile", label: "Perfil", Icon: UserIcon },
];
const SEEN_KEY = "radar.seen";
const CHECK_EVERY = 5 * 60 * 1000;

function feedback(changes: JobChanges, job: Job): string {
  if ("saved" in changes) return changes.saved ? "Guardada" : "Quitada de guardadas";
  if ("applied" in changes) return changes.applied ? "Marcada como aplicada" : "Ya no está como aplicada";
  if ("hidden" in changes) return changes.hidden ? "Descartada" : "Recuperada";
  if ("note" in changes) return job.note ? "Nota guardada" : "Nota borrada";
  return "Hecho";
}

/** What a change looks like before the server answers */
function optimistic(job: Job, changes: JobChanges): Job {
  const stamp = new Date().toISOString();
  const next = { ...job };
  if ("saved" in changes) next.saved_at = changes.saved ? (job.saved_at ?? stamp) : null;
  if ("applied" in changes) {
    next.applied_at = changes.applied ? (job.applied_at ?? stamp) : null;
    if (changes.applied) next.saved_at = next.saved_at ?? stamp;
  }
  if ("hidden" in changes) next.hidden_at = changes.hidden ? (job.hidden_at ?? stamp) : null;
  if ("note" in changes) next.note = changes.note ?? null;
  return next;
}

function readSeen(): number | null {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    return raw == null ? null : Number(raw) || 0;
  } catch {
    return null;
  }
}

export function App() {
  const [config, setConfig] = useState<ServerConfig | null>(loadConfig);
  const api = useMemo(() => (config ? new Api(config) : null), [config]);
  if (!api || !config) {
    return (
      <Welcome
        onSave={(next) => {
          saveConfig(next);
          setConfig(next);
        }}
      />
    );
  }
  return (
    <Shell
      key={config.url + config.token}
      api={api}
      config={config}
      onServer={(next) => {
        saveConfig(next);
        setConfig(next);
      }}
    />
  );
}

function Shell({ api, config, onServer }: { api: Api; config: ServerConfig; onServer: (c: ServerConfig) => void }) {
  const [tab, setTab] = useState<Tab>("home");
  const [open, setOpen] = useState<Job | null>(null);
  const [changed, setChanged] = useState<Record<number, Job>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [seenId, setSeenId] = useState<number>(() => readSeen() ?? 0);
  const [newestId, setNewestId] = useState(0);
  const [unseen, setUnseen] = useState(0);
  const [notify, setNotify] = useState(notifications.loadNotify);
  const [permission, setPermission] = useState<notifications.Permission>("prompt");
  const tabRef = useRef(tab);
  tabRef.current = tab;
  const scrolls = useRef<Record<string, number>>({});

  // each tab, and the list under an open job, keep their scroll position
  const openJob = useCallback((job: Job | null) => {
    if (job) scrolls.current.beforeDetail = window.scrollY;
    setOpen(job);
  }, []);
  useLayoutEffect(() => {
    window.scrollTo(0, open ? 0 : (scrolls.current.beforeDetail ?? 0));
  }, [open]);
  useLayoutEffect(() => {
    window.scrollTo(0, scrolls.current[tab] ?? 0);
  }, [tab]);

  const toast = useCallback((text: string) => {
    setMessage(text);
    window.setTimeout(() => setMessage((current) => (current === text ? null : current)), 2600);
  }, []);

  const change = useCallback(
    async (job: Job, changes: JobChanges): Promise<Job | null> => {
      const before = { ...job };
      setChanged((c) => ({ ...c, [job.id]: optimistic(job, changes) }));
      try {
        const saved = await api.update(job.id, changes);
        setChanged((c) => ({ ...c, [job.id]: saved }));
        toast(feedback(changes, saved));
        return saved;
      } catch (e) {
        setChanged((c) => ({ ...c, [job.id]: before }));
        toast((e as Error).message);
        return null;
      }
    },
    [api, toast],
  );

  const markSeen = useCallback(
    (id: number) => {
      if (id <= 0) return;
      setSeenId(id);
      setUnseen(0);
      try {
        localStorage.setItem(SEEN_KEY, String(id));
      } catch {
        // storage unavailable
      }
    },
    [],
  );

  /** New jobs since the last visit to Novedades, and notifications for new ones */
  const refresh = useCallback(async () => {
    try {
      const stored = readSeen();
      const updates = await api.updates(stored ?? 0, 0, 1);
      setNewestId(updates.newest_id);
      if (stored == null) markSeen(updates.newest_id); // first launch: nothing is "new"
      else setUnseen(updates.total);
      const announced = await notifications.check(api, config);
      if (announced) setReloadKey((k) => k + 1);
    } catch {
      // offline: the lists show the error themselves
    }
  }, [api, config, markSeen]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), CHECK_EVERY);
    let offResume = () => {};
    void notifications
      .onResume(() => {
        void refresh();
        setReloadKey((k) => k + 1);
      })
      .then((off) => (offResume = off));
    return () => {
      window.clearInterval(timer);
      offResume();
    };
  }, [refresh]);

  useEffect(() => {
    void notifications.permission().then(setPermission);
    void notifications.syncRunner(config, notifications.loadNotify());
  }, [config]);

  // tapping a notification: that job, or Novedades
  useEffect(() => {
    let off = () => {};
    void notifications
      .onTap((jobId) => {
        setTab("news");
        if (jobId) api.job(jobId).then(openJob).catch(() => undefined);
      })
      .then((remove) => (off = remove));
    return () => off();
  }, [api, openJob]);

  const updateNotify = useCallback(
    async (changes: Partial<notifications.NotifySettings>) => {
      let next = { ...notifications.loadNotify(), ...changes };
      if (changes.enabled) {
        const result = await notifications.requestPermission();
        setPermission(result);
        if (result !== "granted") {
          toast(result === "denied" ? "Permiso de notificaciones denegado" : "Este dispositivo no admite notificaciones");
          next = { ...next, enabled: false };
        }
      }
      if (next.enabled && !next.lastId) next.lastId = newestId; // only jobs from now on
      notifications.saveNotify(next);
      setNotify(next);
      await notifications.syncRunner(config, next);
      if (changes.enabled && next.enabled) toast("Notificaciones activadas");
    },
    [config, newestId, toast],
  );

  // leaving Novedades marks what was there as seen
  const switchTab = (next: Tab) => {
    scrolls.current[tabRef.current] = window.scrollY;
    if (tabRef.current === "news" && next !== "news") markSeen(newestId);
    if (next === tabRef.current) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      setReloadKey((k) => k + 1);
    }
    setTab(next);
  };

  // Android back: close the job, then go home, then leave the app
  const back = useRef<() => boolean>(() => false);
  back.current = () => {
    if (open) {
      openJob(null);
      return true;
    }
    if (tab !== "home") {
      switchTab("home");
      return true;
    }
    return false;
  };
  useEffect(() => {
    let off = () => {};
    void onBackButton(() => back.current()).then((unsubscribe) => (off = unsubscribe));
    return () => off();
  }, []);

  const refreshAll = useCallback(() => {
    setChanged({}); // their compatibility changed too: take the server's
    setReloadKey((k) => k + 1);
  }, []);
  const ctx: AppCtx = { api, changed, open: openJob, change, toast, seenId, refreshAll };
  return (
    <Ctx.Provider value={ctx}>
      <div className="app" hidden={Boolean(open)}>
        <div hidden={tab !== "home"}>
          <Home reloadKey={reloadKey} />
        </div>
        <div hidden={tab !== "jobs"}>
          <JobsScreen reloadKey={reloadKey} />
        </div>
        <div hidden={tab !== "news"}>
          <News
            reloadKey={reloadKey}
            unseen={unseen}
            notificationsOn={notify.enabled && permission === "granted"}
            onEnableNotifications={() => void updateNotify({ enabled: true })}
            onMarkSeen={() => markSeen(newestId)}
          />
        </div>
        <div hidden={tab !== "profile"}>
          <ProfileScreen
            config={config}
            onServer={onServer}
            notify={notify}
            permission={permission}
            onNotify={(c) => void updateNotify(c)}
            onTestNotification={() => void notifications.test()}
            reloadKey={reloadKey}
          />
        </div>
        <nav className="bottom-nav">
          {TABS.map(({ name, label, Icon }) => (
            <button key={name} className={tab === name ? "nav-item on" : "nav-item"} onClick={() => switchTab(name)} aria-label={label}>
              <span className="nav-icon">
                <Icon size={24} />
                {name === "news" && unseen > 0 && <span className="badge">{unseen > 99 ? "99+" : unseen}</span>}
              </span>
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </div>
      {open && <Detail job={changed[open.id] ?? open} onBack={() => openJob(null)} />}
      {message && <div className="toast">{message}</div>}
    </Ctx.Provider>
  );
}
