import { useEffect, useState } from "react";
import type { ListName, Stats } from "./api";
import { useApp } from "./context";
import { useDebounced } from "./hooks";
import { CloseIcon, SearchIcon } from "./icons";
import { JobList } from "./JobList";

type View = "home" | ListName;

export function Home({ reloadKey }: { reloadKey: number }) {
  const { api } = useApp();
  const [typed, setTyped] = useState("");
  const [remote, setRemote] = useState(false);
  const [good, setGood] = useState(false);
  const [view, setView] = useState<View>("home");
  const [stats, setStats] = useState<Stats | null>(null);
  const q = useDebounced(typed.trim());

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats(null));
  }, [api, reloadKey]);

  const filtering = Boolean(q || remote || good);
  const filters = { q, remote, minMatch: good ? 70 : 0 };

  return (
    <div className="page">
      <section className="hero">
        <h1>{view === "top" ? "Más compatibles" : view === "recent" ? "Últimas ofertas" : "Encuentra tu próximo empleo"}</h1>
        {stats && view === "home" && (
          <p className="hero-sub">
            {stats.total} ofertas · {stats.week} nuevas esta semana · {stats.good_week} muy compatibles
          </p>
        )}
        <label className="search-box">
          <SearchIcon size={20} />
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="Puesto, empresa, tecnología…"
            enterKeyHint="search"
            autoCorrect="off"
          />
          {typed && (
            <button className="icon-btn" onClick={() => setTyped("")} aria-label="Borrar búsqueda">
              <CloseIcon size={18} />
            </button>
          )}
        </label>
        <div className="filter-chips">
          <button className={remote ? "fchip on" : "fchip"} onClick={() => setRemote(!remote)}>
            Teletrabajo
          </button>
          <button className={good ? "fchip on" : "fchip"} onClick={() => setGood(!good)}>
            70%+ compatibles
          </button>
        </div>
      </section>

      <div className="page-body">
        {filtering ? (
          <>
            <ListTitle title={q ? `Resultados de «${q}»` : "Resultados"} />
            <JobList list={view === "home" ? "recent" : view} filters={filters} empty="Nada coincide con la búsqueda." reloadKey={reloadKey} />
          </>
        ) : view !== "home" ? (
          <>
            <button className="text-btn back-link" onClick={() => setView("home")}>
              ‹ Inicio
            </button>
            <JobList
              list={view}
              empty={view === "top" ? "No hay ofertas nuevas sin aplicar en los últimos 7 días." : "Aún no hay ofertas."}
              reloadKey={reloadKey}
            />
          </>
        ) : (
          <>
            <ListTitle title="Más compatibles para ti" action="Ver todas" onAction={() => setView("top")} />
            <JobList list="top" limit={3} empty="Sin ofertas nuevas sin aplicar esta semana." reloadKey={reloadKey} />
            <ListTitle title="Últimas ofertas" action="Ver todas" onAction={() => setView("recent")} />
            <JobList list="recent" limit={10} empty="Aún no hay ofertas: llegarán con la próxima búsqueda." reloadKey={reloadKey} />
            <button className="wide" onClick={() => setView("recent")}>
              Ver todas las ofertas
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export function ListTitle({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  return (
    <div className="list-title">
      <h2>{title}</h2>
      {action && (
        <button className="text-btn" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}
