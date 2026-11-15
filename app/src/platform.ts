// Native bits through Capacitor, with browser fallbacks so the app also runs in a
// browser (npm run dev). The plugins load lazily: on the web they may be missing.

type Unsubscribe = () => void;

function isNative(): boolean {
  const cap = (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
  return Boolean(cap?.isNativePlatform?.());
}

/** Android's back button: the handler returns true when it went back a screen */
export async function onBackButton(handler: () => boolean): Promise<Unsubscribe> {
  if (!isNative()) return () => {};
  try {
    const { App } = await import("@capacitor/app");
    const listener = await App.addListener("backButton", () => {
      if (!handler()) void App.minimizeApp();
    });
    return () => void listener.remove();
  } catch {
    return () => {};
  }
}

/** Opens a job's page in the phone's browser */
export function openExternal(url: string): void {
  window.open(url, "_blank", "noopener");
}

/** Hands a CSV to Android's share sheet (Drive, mail, files...) or downloads it */
export async function shareCsv(name: string, csv: string): Promise<void> {
  if (isNative()) {
    const { Filesystem, Directory, Encoding } = await import("@capacitor/filesystem");
    const { Share } = await import("@capacitor/share");
    const file = await Filesystem.writeFile({
      path: name,
      data: csv,
      directory: Directory.Cache,
      encoding: Encoding.UTF8,
    });
    await Share.share({ title: name, url: file.uri });
    return;
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
}

/** Opens a PDF (base64): Android offers its PDF viewers; the browser opens a tab */
export async function openPdf(name: string, base64: string): Promise<void> {
  if (isNative()) {
    const { Filesystem, Directory } = await import("@capacitor/filesystem");
    const { Share } = await import("@capacitor/share");
    const file = await Filesystem.writeFile({ path: name, data: base64, directory: Directory.Cache });
    await Share.share({ title: name, url: file.uri });
    return;
  }
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
