// Run once after `npx cap add android` (npm run android:add does it):
// - lets the app call a plain http:// server (your Tailscale address on port 8000);
//   not needed if you use `tailscale serve` (https)
// - declares the notifications permission Android 13+ asks for
import { readFileSync, writeFileSync } from "node:fs";

const path = "android/app/src/main/AndroidManifest.xml";
let manifest = readFileSync(path, "utf8");
const done = [];
if (!manifest.includes("usesCleartextTraffic")) {
  manifest = manifest.replace("<application", '<application\n        android:usesCleartextTraffic="true"');
  done.push("allowed http:// traffic");
}
if (!manifest.includes("android.permission.POST_NOTIFICATIONS")) {
  manifest = manifest.replace(
    "</manifest>",
    '    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n</manifest>',
  );
  done.push("declared POST_NOTIFICATIONS");
}
writeFileSync(path, manifest);
console.log(`AndroidManifest.xml: ${done.length ? done.join(", ") : "already set up"}`);
