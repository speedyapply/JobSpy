// Runs in the background (@capacitor/background-runner), about every 15 minutes, even
// with the app closed: asks the server for jobs newer than the last one announced and
// shows a notification. The app hands it the server and settings with "configure".
// This file runs in the runner's own small JavaScript engine: no imports, no DOM.

function read(key, fallback) {
  try {
    const item = CapacitorKV.get(key);
    return item && item.value != null ? item.value : fallback;
  } catch (e) {
    return fallback;
  }
}

addEventListener("configure", (resolve, reject, args) => {
  try {
    const d = args || {};
    CapacitorKV.set("url", String(d.url || ""));
    CapacitorKV.set("token", String(d.token || ""));
    CapacitorKV.set("enabled", d.enabled ? "1" : "0");
    CapacitorKV.set("minMatch", String(d.minMatch || 0));
    // never go back: the app or this runner may have announced newer jobs
    const last = Math.max(Number(read("lastId", "0")) || 0, Number(d.lastId) || 0);
    CapacitorKV.set("lastId", String(last));
    resolve({ lastId: last });
  } catch (e) {
    reject(e);
  }
});

addEventListener("state", (resolve) => {
  resolve({ lastId: Number(read("lastId", "0")) || 0 });
});

addEventListener("checkJobs", async (resolve, reject) => {
  try {
    const url = read("url", "");
    if (read("enabled", "0") !== "1" || !url) {
      resolve();
      return;
    }
    const after = Number(read("lastId", "0")) || 0;
    const minMatch = Number(read("minMatch", "0")) || 0;
    const token = read("token", "");
    const headers = { Accept: "application/json" };
    if (token) headers.Authorization = "Bearer " + token;
    const response = await fetch(
      url + "/api/updates?after=" + after + "&min_match=" + minMatch + "&limit=3",
      { headers: headers },
    );
    if (!response.ok) {
      resolve();
      return;
    }
    const updates = await response.json();
    CapacitorKV.set("lastId", String(Math.max(after, Number(updates.newest_id) || 0)));
    if (after === 0 || !updates.total) {
      resolve();
      return;
    }
    const jobs = updates.jobs || [];
    const pct = (j) => (j.match == null ? "" : j.match + "% · ");
    let title;
    let body;
    if (updates.total === 1 && jobs[0]) {
      title = pct(jobs[0]) + jobs[0].title;
      body = [jobs[0].company, jobs[0].location].filter(Boolean).join(" · ") || "Nueva oferta";
    } else {
      title = updates.total + " ofertas nuevas";
      body = jobs.slice(0, 3).map((j) => pct(j) + j.title).join("\n");
    }
    CapacitorNotifications.schedule([
      { id: Date.now() % 2147483647, title: title, body: body, scheduleAt: new Date() },
    ]);
    resolve();
  } catch (e) {
    // offline or Tailscale off: try again next time
    resolve();
  }
});
