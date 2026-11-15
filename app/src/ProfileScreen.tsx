import { useCallback, useEffect, useRef, useState } from "react";
import type { CvInfo, Profile, ServerConfig, Stats } from "./api";
import { useApp } from "./context";
import { when } from "./format";
import { CloseIcon, FileIcon } from "./icons";
import type { NotifySettings, Permission } from "./notifications";
import { openPdf, shareCsv } from "./platform";
import { ServerForm } from "./Settings";

const ENGLISH = ["", "A1", "A2", "B1", "B2", "C1", "C2"];

function size(bytes: number): string {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(new Error("No se pudo leer el archivo"));
    reader.readAsDataURL(file);
  });
}

/** Editable list of words: tap × to remove, type and Enter (or ,) to add */
function ChipEditor({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  const [text, setText] = useState("");
  const add = () => {
    const items = text
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter((t) => t && !value.includes(t));
    if (items.length) onChange([...value, ...items]);
    setText("");
  };
  return (
    <div className="chip-editor">
      {value.map((v) => (
        <span key={v} className="chip edit">
          {v}
          <button aria-label={`Quitar ${v}`} onClick={() => onChange(value.filter((x) => x !== v))}>
            <CloseIcon size={14} />
          </button>
        </span>
      ))}
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
        placeholder={placeholder}
        enterKeyHint="done"
        autoCapitalize="off"
      />
    </div>
  );
}

export function ProfileScreen({
  config,
  onServer,
  notify,
  permission,
  onNotify,
  onTestNotification,
  reloadKey,
}: {
  config: ServerConfig;
  onServer: (config: ServerConfig) => void;
  notify: NotifySettings;
  permission: Permission;
  onNotify: (settings: Partial<NotifySettings>) => void;
  onTestNotification: () => void;
  reloadKey: number;
}) {
  const { api, toast, refreshAll } = useApp();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [saved, setSaved] = useState<string>("");
  const [cv, setCv] = useState<CvInfo | null | undefined>(undefined);
  const [stats, setStats] = useState<Stats | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showServer, setShowServer] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .profile()
      .then((p) => {
        setProfile(p);
        setSaved(JSON.stringify(p));
      })
      .catch((e: Error) => setError(e.message));
    api.cvInfo().then(setCv).catch(() => setCv(null));
    api.stats().then(setStats).catch(() => setStats(null));
  }, [api]);
  useEffect(load, [load, reloadKey]);

  const dirty = profile != null && JSON.stringify(profile) !== saved;
  const edit = (changes: Partial<Profile>) => setProfile((p) => (p ? { ...p, ...changes } : p));

  const saveProfile = async () => {
    if (!profile) return;
    setBusy("profile");
    try {
      const result = await api.saveProfile(profile);
      const { rescored, ...clean } = result;
      setProfile(clean);
      setSaved(JSON.stringify(clean));
      toast(`Perfil guardado · compatibilidad recalculada en ${rescored} ofertas`);
      refreshAll();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (file.type && file.type !== "application/pdf") {
      toast("El CV tiene que ser un PDF");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast("El CV pesa más de 10 MB");
      return;
    }
    setBusy("cv");
    try {
      setCv(await api.uploadCv(file.name, await readBase64(file)));
      toast("CV subido");
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const viewCv = async () => {
    setBusy("view");
    try {
      const { name, data } = await api.cv();
      await openPdf(name, data);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const removeCv = async () => {
    if (!window.confirm("¿Eliminar el CV del servidor?")) return;
    try {
      await api.deleteCv();
      setCv(null);
      toast("CV eliminado");
    } catch (e) {
      toast((e as Error).message);
    }
  };

  const exportCsv = async () => {
    setBusy("export");
    try {
      const csv = await api.exportCsv();
      if (csv.split("\n").filter((l) => l.trim()).length <= 1) toast("No hay ofertas guardadas ni aplicadas");
      else await shareCsv("ofertas_guardadas.csv", csv);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>Perfil</h1>
        <p className="muted small">Tu CV y lo que usa el servidor para calcular la compatibilidad.</p>
      </header>
      <div className="page-body">
        {error && (
          <div className="error-box">
            <p>{error}</p>
            <button onClick={load}>Reintentar</button>
          </div>
        )}

        <section className="panel">
          <h2>Currículum</h2>
          {cv === undefined ? (
            <p className="muted">Cargando…</p>
          ) : cv ? (
            <>
              <div className="cv-file">
                <FileIcon size={32} />
                <div>
                  <b>{cv.name}</b>
                  <span className="muted small">
                    {size(cv.size)} · subido {when(cv.uploaded_at)}
                  </span>
                </div>
              </div>
              <div className="row">
                <button disabled={busy === "view"} onClick={() => void viewCv()}>
                  {busy === "view" ? "Abriendo…" : "Ver"}
                </button>
                <button disabled={busy === "cv"} onClick={() => fileInput.current?.click()}>
                  {busy === "cv" ? "Subiendo…" : "Cambiar"}
                </button>
                <button className="danger" onClick={() => void removeCv()}>
                  Eliminar
                </button>
              </div>
              {profile && cv.suggested.length > 0 && (
                <div className="suggest">
                  <p className="small">Tu CV menciona estas tecnologías que no están en tus habilidades:</p>
                  <div className="chips">
                    {cv.suggested
                      .filter((s) => !profile.skills.includes(s))
                      .map((s) => (
                        <button key={s} className="chip add" onClick={() => edit({ skills: [...profile.skills, s] })}>
                          + {s}
                        </button>
                      ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <button className="wide primary" disabled={busy === "cv"} onClick={() => fileInput.current?.click()}>
              {busy === "cv" ? "Subiendo…" : "Subir CV (PDF)"}
            </button>
          )}
          <input ref={fileInput} type="file" accept="application/pdf" hidden onChange={(e) => void upload(e.target.files?.[0])} />
        </section>

        {profile && (
          <section className="panel form">
            <h2>Información</h2>
            <label>
              Habilidades
              <ChipEditor value={profile.skills} onChange={(skills) => edit({ skills })} placeholder="Añadir: react, docker…" />
            </label>
            <label>
              Puestos que buscas
              <ChipEditor value={profile.roles} onChange={(roles) => edit({ roles })} placeholder="Añadir: full stack, frontend…" />
            </label>
            <label>
              Ubicaciones
              <ChipEditor value={profile.locations} onChange={(locations) => edit({ locations })} placeholder="Añadir: las palmas…" />
            </label>
            <div className="row">
              <label>
                Años de experiencia
                <input
                  type="number"
                  min={0}
                  max={60}
                  step={0.5}
                  value={profile.years_experience}
                  onChange={(e) => edit({ years_experience: Math.max(0, Math.min(60, Number(e.target.value) || 0)) })}
                />
              </label>
              <label>
                Inglés
                <select value={profile.english} onChange={(e) => edit({ english: e.target.value })}>
                  {ENGLISH.map((level) => (
                    <option key={level} value={level}>
                      {level || "—"}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="switch">
              <input type="checkbox" checked={profile.remote_ok} onChange={(e) => edit({ remote_ok: e.target.checked })} />
              Acepto teletrabajo
            </label>
            <button className="wide primary" disabled={!dirty || busy === "profile"} onClick={() => void saveProfile()}>
              {busy === "profile" ? "Guardando…" : dirty ? "Guardar cambios" : "Guardado"}
            </button>
          </section>
        )}

        <section className="panel form">
          <h2>Notificaciones</h2>
          <label className="switch">
            <input type="checkbox" checked={notify.enabled} onChange={(e) => onNotify({ enabled: e.target.checked })} />
            Avisarme de ofertas nuevas
          </label>
          {permission === "denied" && (
            <p className="error small">El permiso está denegado: actívalo en Ajustes de Android › Apps › Radar de Ofertas.</p>
          )}
          {permission === "unsupported" && <p className="muted small">Este dispositivo no admite notificaciones.</p>}
          <label>
            Solo si son compatibles al menos
            <select value={notify.minMatch} onChange={(e) => onNotify({ minMatch: Number(e.target.value) })}>
              <option value={0}>Todas las ofertas</option>
              <option value={45}>45% o más</option>
              <option value={60}>60% o más</option>
              <option value={70}>70% o más</option>
              <option value={85}>85% o más</option>
            </select>
          </label>
          <button disabled={!notify.enabled || permission !== "granted"} onClick={onTestNotification}>
            Enviar notificación de prueba
          </button>
          <p className="muted small">
            Con la app cerrada, Android la revisa cada 15 minutos aproximadamente. El móvil tiene que tener Tailscale conectado.
          </p>
        </section>

        {stats && (
          <section className="panel">
            <h2>Resumen</h2>
            <div className="tiles">
              <div className="tile">
                <b>{stats.total}</b>
                <span>ofertas</span>
              </div>
              <div className="tile">
                <b>{stats.saved}</b>
                <span>guardadas</span>
              </div>
              <div className="tile">
                <b>{stats.applied}</b>
                <span>aplicadas</span>
              </div>
            </div>
            <dl className="facts">
              {Object.entries(stats.sites).map(([site, n]) => (
                <div key={site} className="contents">
                  <dt>{site}</dt>
                  <dd>{n} ofertas</dd>
                </div>
              ))}
              <dt>Búsquedas</dt>
              <dd>cada {stats.interval_hours} h · próxima {when(stats.next_run)}</dd>
            </dl>
            <button className="wide" disabled={busy === "export"} onClick={() => void exportCsv()}>
              {busy === "export" ? "Exportando…" : "Exportar guardadas y aplicadas (CSV)"}
            </button>
          </section>
        )}

        <section className="panel">
          <h2>Servidor</h2>
          <p className="muted small break">{config.url}</p>
          {showServer ? (
            <ServerForm
              initial={config}
              onSave={(next) => {
                onServer(next);
                setShowServer(false);
              }}
            />
          ) : (
            <button onClick={() => setShowServer(true)}>Cambiar servidor</button>
          )}
        </section>
      </div>
    </div>
  );
}
