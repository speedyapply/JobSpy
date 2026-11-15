# Radar de Ofertas (app)

React + Capacitor app for Android that reads the backend in `../runner` (`api.py`) over
Tailscale. It never contacts the job boards itself: everything comes from your server.

- **Inicio**: search box with filters (remote, 70%+), your best matches and the latest jobs
- **Empleos**: saved, applied and discarded jobs
- **Novedades**: jobs since your last visit (badge on the tab), last and next search,
  and a nudge to turn notifications on
- **Perfil**: your CV (upload, view, replace; the skills it names are suggested), the
  profile the compatibility score uses (skills, roles, years, places, English, remote),
  notifications, a summary with CSV export, and the server
- A job: compatibility (what you have, lack, and warnings), mark applied / discard /
  save, your notes, the description, and a button to its page

## Notifications

There's no push service in between: the phone asks the server for jobs newer than the
last one it announced (`/api/updates`) when the app opens or comes back, every 5 minutes
while open, and about every 15 minutes with the app closed, through
`@capacitor/background-runner` (`public/runners/background.js`). Several new jobs make
one notification. Turn them on in Novedades or Perfil, where you can also set a minimum
compatibility. For it to work with the app closed, Tailscale must stay connected on the
phone, and Android must not put the app to sleep: Settings › Apps › Radar de Ofertas ›
Battery › Unrestricted.

## 1. The server on Tailscale

On the machine running Docker:

```bash
cp .env.example .env                 # set API_TOKEN (any long random text)
docker compose up -d --build         # the API listens on port 8000
```

Install Tailscale on that machine and on your phone, with the same account. Then the
app's server address is one of:

- `http://<machine-name>:8000` with MagicDNS on, or `http://100.x.y.z:8000`
  (`tailscale ip -4` on the machine);
- **recommended**, HTTPS without touching Android's settings: run
  `tailscale serve --bg 8000` on the machine, and use
  `https://<machine-name>.<your-tailnet>.ts.net` (the address `tailscale serve status` prints).

## 2. Try it in the browser

```bash
npm install
npm run dev          # http://localhost:5173, set the server in ⚙
```

## 3. Android

Needs [Android Studio](https://developer.android.com/studio) (it brings the SDK and JDK).

```bash
npm install
npm run build
npm run android:add      # once: creates android/, allows http:// addresses and
                         # declares the notifications permission
npm run android:sync     # after every change to the app
npm run android:open     # opens Android Studio: ▶ Run to your phone, or
                         # Build > Generate App Bundles or APKs > Generate APKs
```

With the phone plugged in by USB (developer mode on), `npm run android:run` builds and
installs in one step.

On first launch the app asks for the server address and the token; ⚙ changes them later.

## What's where

| | |
|---|---|
| `src/api.ts` | the API client and its types |
| `src/App.tsx` | the tabs, the bottom bar, shared state, checks for new jobs |
| `src/Home.tsx`, `JobsScreen.tsx`, `News.tsx`, `ProfileScreen.tsx` | the four tabs |
| `src/JobCard.tsx`, `JobList.tsx` | a job in a list; a paged list of them |
| `src/Detail.tsx` | a job in full |
| `src/Settings.tsx` | server address and token |
| `src/notifications.ts`, `public/runners/background.js` | notifications, open and closed |
| `src/platform.ts` | Android back button, opening links and PDFs, sharing the CSV |

The app uses Capacitor 7. If you move to a newer Capacitor, update every `@capacitor/*`
package (and `@capacitor/background-runner` to its matching major) together.
