import { useCallback, useEffect, useState } from "react";
import type { ListName, Stats } from "./api";
import { useApp } from "./context";
import { JobList } from "./JobList";

const SEGMENTS: { name: ListName; label: string; key: keyof Stats; empty: string }[] = [
  { name: "saved", label: "Guardadas", key: "saved", empty: "Pulsa la estrella de una oferta para guardarla y verla aquí." },
  { name: "applied", label: "Aplicadas", key: "applied", empty: "Cuando marques una oferta como aplicada aparecerá aquí." },
  { name: "hidden", label: "Descartadas", key: "hidden", empty: "No has descartado ninguna oferta." },
];

export function JobsScreen({ reloadKey }: { reloadKey: number }) {
  const { api, changed } = useApp();
  const [segment, setSegment] = useState<ListName>("saved");
  const [stats, setStats] = useState<Stats | null>(null);

  const loadStats = useCallback(() => {
    api.stats().then(setStats).catch(() => setStats(null));
  }, [api]);
  useEffect(loadStats, [loadStats, reloadKey, changed]);

  return (
    <div className="page">
      <header className="page-header">
        <h1>Mis empleos</h1>
        <div className="segments" role="tablist">
          {SEGMENTS.map((s) => (
            <button
              key={s.name}
              role="tab"
              aria-selected={segment === s.name}
              className={segment === s.name ? "segment on" : "segment"}
              onClick={() => setSegment(s.name)}
            >
              {s.label}
              {stats ? <span className="count">{String(stats[s.key])}</span> : null}
            </button>
          ))}
        </div>
      </header>
      <div className="page-body">
        <JobList key={segment} list={segment} empty={SEGMENTS.find((s) => s.name === segment)!.empty} reloadKey={reloadKey} />
      </div>
    </div>
  );
}
