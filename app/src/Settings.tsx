import { useState } from "react";
import { Api, normaliseUrl, type ServerConfig } from "./api";

/** Server address and token: the first screen, and a section of the profile */
export function ServerForm({ initial, onSave }: { initial: ServerConfig | null; onSave: (config: ServerConfig) => void }) {
  const [url, setUrl] = useState(initial?.url ?? "");
  const [token, setToken] = useState(initial?.token ?? "");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const config = (): ServerConfig => ({ url: normaliseUrl(url), token: token.trim() });

  const test = async (): Promise<boolean> => {
    if (!url.trim()) {
      setStatus({ ok: false, text: "Escribe la dirección del servidor." });
      return false;
    }
    setTesting(true);
    setStatus(null);
    try {
      const health = await new Api(config()).health();
      setStatus({ ok: true, text: `Conectado: ${health.jobs} ofertas guardadas${health.running ? ", buscando ahora mismo" : ""}.` });
      return true;
    } catch (e) {
      setStatus({ ok: false, text: (e as Error).message });
      return false;
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="form">
      <label>
        Dirección del servidor
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="http://mi-pc:8000"
          inputMode="url"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
        />
      </label>
      <label>
        Token (API_TOKEN del .env)
        <input
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="vacío si no usas token"
          type="password"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
        />
      </label>
      {status && <p className={status.ok ? "ok" : "error"}>{status.text}</p>}
      <div className="row">
        <button disabled={testing} onClick={() => void test()}>
          {testing ? "Probando…" : "Probar conexión"}
        </button>
        <button className="primary" disabled={testing} onClick={() => void test().then((ok) => ok && onSave(config()))}>
          Guardar
        </button>
      </div>
    </div>
  );
}

/** First launch: no server yet */
export function Welcome({ onSave }: { onSave: (config: ServerConfig) => void }) {
  return (
    <div className="page welcome">
      <section className="hero">
        <h1>Radar de Ofertas</h1>
        <p className="hero-sub">Conecta la app con tu servidor para ver tus ofertas.</p>
      </section>
      <div className="page-body">
        <p className="muted">
          La dirección de tu backend en Tailscale, por ejemplo <code>http://mi-pc:8000</code> o, con{" "}
          <code>tailscale serve</code>, <code>https://mi-pc.tu-tailnet.ts.net</code>.
        </p>
        <ServerForm initial={null} onSave={onSave} />
      </div>
    </div>
  );
}
