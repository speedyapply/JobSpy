import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "es.mansour.radarofertas",
  appName: "Radar de Ofertas",
  webDir: "dist",
  plugins: {
    // native HTTP: no CORS, and the app (served from https://localhost) can call an
    // http:// Tailscale address without the WebView blocking it as mixed content
    CapacitorHttp: { enabled: true },
    // checks the server for new jobs every 15 minutes, even with the app closed
    BackgroundRunner: {
      label: "es.mansour.radarofertas.check",
      src: "runners/background.js",
      event: "checkJobs",
      repeat: true,
      interval: 15,
      autoStart: true,
    },
    LocalNotifications: {
      iconColor: "#1565c0",
    },
  },
};

export default config;
