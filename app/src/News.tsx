import { useEffect, useState } from "react";
import type { Stats } from "./api";
import { useApp } from "./context";
import { ago, when } from "./format";
import { BellIcon } from "./icons";
import { JobList } from "./JobList";
import { ListTitle } from "./Home";

export function News({
  reloadKey,
  unseen,
  notificationsOn,
  onEnableNotifications,
  onMarkSeen,
}: {
  reloadKey: number;
  unseen: number;
  notificationsOn: boolean;
  onEnableNotifications: () => void;
  onMarkSeen: () => void;
}) {
  const { api } = useApp();
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats(null));
  }, [api, reloadKey]);

  const result = stats?.last_run_result;
  return (
    <div className="page">
      <header className="page-header">
        <h1>Novedades</h1>
        {stats && (
          <p className="muted small">
            {stats.running
              ? "Buscando ofertas ahora mismo…"
              : `Última búsqueda ${ago(stats.last_run) ?? "—"} (${when(stats.last_run)})${result ? ` · ${result.new} nuevas` : ""}`}
            {stats.next_run && !stats.running ? ` · próxima ${when(stats.next_run)}` : ""}
          </p>
        )}
      </header>
      <div className="page-body">
        {!notificationsOn && (
          <div className="promo">
            <BellIcon size={28} />
            <div>
              <b>Activa las notificaciones</b>
              <p>Te avisaré en cuanto el servidor encuentre ofertas nuevas.</p>
            </div>
            <button className="primary" onClick={onEnableNotifications}>
              Activar
            </button>
          </div>
        )}
        {result?.errors.length ? (
          <div className="warn-box">
            <b>La última búsqueda tuvo problemas</b>
            {result.errors.map((e) => (
              <p key={e}>{e}</p>
            ))}
          </div>
        ) : null}
        <ListTitle
          title={unseen ? `${unseen} oferta${unseen === 1 ? "" : "s"} sin ver` : "Todo al día"}
          action={unseen ? "Marcar como vistas" : undefined}
          onAction={onMarkSeen}
        />
        <JobList list="recent" empty="Aún no hay ofertas: llegarán con la próxima búsqueda." reloadKey={reloadKey} />
      </div>
    </div>
  );
}
