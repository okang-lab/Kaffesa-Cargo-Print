#!/usr/bin/env node
// Kaffesa Personel (/app/) derleme betiği
//
// Kullanım:
//   node build.mjs                      -> şifreyi sorar (en az 4 karakter; sadece rakamsa telefonda rakam klavyesi açılır)
//   APP_PASSWORD='...' node build.mjs   -> şifreyi ortam değişkeninden alır
//
// Çıktı: dist/app/index.html  (kaffesa.com sitesinin kökündeki app/ klasörüne kopyalanır)
// Ek paket gerekmez; Node 18+ yeterli.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { webcrypto as crypto } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import readline from "node:readline";

const ROOT = dirname(fileURLToPath(import.meta.url));
const r = (p, enc) => readFileSync(join(ROOT, p), enc);
const b64 = (buf) => Buffer.from(buf).toString("base64");
const ITERATIONS = 600000;

function pngSize(buf) {
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

// "</script" dizisi satır içi <script> bloğunu erken kapatmasın
const inlineJs = (s) => s.replace(/<\/script/gi, "<\\/script");
// replace() içindeki $ özel karakterlerinden etkilenmeden yer değiştir
const fill = (tpl, map) => Object.entries(map).reduce((t, [k, v]) => t.split(`{{${k}}}`).join(v), tpl);

function askPassword() {
  if (process.env.APP_PASSWORD) return Promise.resolve(process.env.APP_PASSWORD);
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    rl._writeToOutput = (s) => { if (!rl.muted) rl.output.write(s); };
    rl.question("Personel şifresi: ", (pw) => { rl.close(); process.stdout.write("\n"); resolve(pw); });
    rl.muted = true;
  });
}

async function encrypt(plaintext, password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations: ITERATIONS },
    base, { name: "AES-GCM", length: 256 }, false, ["encrypt"]
  );
  const data = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(plaintext));
  return { v: 1, iter: ITERATIONS, salt: b64(salt), iv: b64(iv), data: b64(data) };
}

const password = await askPassword();
if (!password || password.length < 4) {
  console.error("Şifre en az 4 karakter olmalı.");
  process.exit(1);
}

const logo = r("assets/logo.png");
const logoSize = pngSize(logo);
const assets = {
  fontBase64: b64(r("assets/DejaVuSans-tr.ttf")),
  logoBase64: b64(logo),
  logoWidth: logoSize.width,
  logoHeight: logoSize.height,
};
const logoUi = b64(r("assets/logo-ui.png"));

const app = fill(r("src/app.html", "utf8"), {
  LOGO_UI: logoUi,
  JSPDF: inlineJs(r("vendor/jspdf.umd.min.js", "utf8")),
  CORE_JS: inlineJs(r("src/kargo-core.js", "utf8")),
  ASSETS_JSON: inlineJs(JSON.stringify(assets)),
});

const payload = await encrypt(app, password);
// Şifre sadece rakamsa telefonda rakam klavyesi açılsın
const inputMode = /^\d+$/.test(password) ? "numeric" : "text";
const out = fill(r("src/lock.html", "utf8"), { LOGO_UI: logoUi, PAYLOAD: JSON.stringify(payload), INPUTMODE: inputMode });

mkdirSync(join(ROOT, "dist/app"), { recursive: true });
writeFileSync(join(ROOT, "dist/app/index.html"), out);
console.log(`Hazır: dist/app/index.html (${(out.length / 1024).toFixed(0)} KB)`);
