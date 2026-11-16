/*
 * Kaffesa Kargo Etiket — çekirdek (tarayıcı + Node)
 * index.py (Streamlit/ReportLab) sürümündeki mantığın ve ölçülerin birebir JS karşılığı.
 * Bağımlılık: jsPDF 2.x  (tarayıcıda window.jspdf, Node'da require('jspdf'))
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KargoCore = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const MM = 72 / 25.4;

  // Excel sütunları (0 tabanlı) — Kasım 2026 düzeni: J=Alıcı, R=Adres, S=Telefon, T=ÜA/ÜG
  const COL_NAME = 9;
  const COL_ADDRESS = 17;
  const COL_PHONE = 18;
  const COL_PAYMENT = 19;
  const MIN_COLUMN_COUNT = 20;

  const ISTANBUL_INFO =
    "KAFFESA GIDA SANAYİ VE DIŞ TİCARET ANONİM ŞİRKETİ\n" +
    "Adres: BALMUMCU MAH. BARBAROS BULVARI İBA BLOKLARI, 34/A\n" +
    "İl/İlçe: Beşiktaş/İstanbul\n" +
    "Tel: 0212 265 16 16\n";

  const ANKARA_INFO =
    "KAFFESA GIDA SANAYİ VE DIŞ TİCARET ANONİM ŞİRKETİ\n" +
    "Adres: TURAN GÜNEŞ BULVARI 55/3\n" +
    "İl/İlçe: Çankaya / Ankara\n" +
    "Tel: 0312 476 16 16 / +90 537 472 59 48\n";

  // ---------------------------------------------------------------------------
  // Yardımcılar
  // ---------------------------------------------------------------------------
  function normalizePayToken(token) {
    if (typeof token !== "string") return null;
    const t = token.normalize("NFKC").trim().toLowerCase().replace(/ /g, "");
    if (t === "üa" || t === "ua") return "ÜA";
    if (t === "üg" || t === "ug") return "ÜG";
    return null;
  }

  // 10 haneli ve 0 / +90 ile başlamayan numaraların başına 0 ekler: (542) 647 99 33 -> 0 (542) 647 99 33
  function normalizePhone(phone) {
    const s = String(phone || "").trim();
    if (s.replace(/\D/g, "").length === 10 && !/^[0+]/.test(s)) return "0 " + s;
    return s;
  }

  function sanitizeFilename(s) {
    s = String(s || "").replace(/[^\p{L}\p{N}_\s-]/gu, "").trim();
    return s.replace(/\s+/g, "_").slice(0, 60) || "etiket";
  }

  function pageSize(name) {
    if (name === "100x100") return [100 * MM, 100 * MM];
    if (name === "A4") return [595.2755905511812, 841.8897637795277];
    return [148 * MM, 210 * MM]; // A5
  }

  // Excel'den kopyalanan TAB ayrımlı metni okur. Excel'in tırnaklı hücrelerini
  // (hücre içi satır sonu vb.) pandas gibi tek hücre olarak tanır.
  function parseTSV(text) {
    const rows = [];
    let row = [], field = "", inQuotes = false, atStart = true;
    const n = text.length;
    for (let i = 0; i < n; i++) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else inQuotes = false;
        } else field += c;
        continue;
      }
      if (atStart && c === '"') { inQuotes = true; atStart = false; continue; }
      if (c === "\t") { row.push(field); field = ""; atStart = true; continue; }
      if (c === "\r" || c === "\n") {
        row.push(field); rows.push(row);
        row = []; field = ""; atStart = true;
        if (c === "\r" && text[i + 1] === "\n") i++;
        continue;
      }
      field += c; atStart = false;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    return rows;
  }

  // Yapıştırılan veriden alıcı kayıtlarını çıkarır (yalnızca I/Q/R/S).
  function parseRecipients(raw) {
    const result = { rows: [], errorLines: 0 };
    if (!raw) return result;
    // pandas gibi: tablo genişliği en geniş satır kadar, kısa satırlar boş hücreyle tamamlanır
    const all = parseTSV(raw).filter((cells) => !cells.every((c) => c.trim() === "")); // boş satırlar
    const tableWidth = all.reduce((m, cells) => Math.max(m, cells.length), 0);
    for (const cells of all) {
      if (tableWidth < MIN_COLUMN_COUNT) { result.errorLines++; continue; }
      const name = (cells[COL_NAME] || "").trim();
      if (!name) { result.errorLines++; continue; }
      result.rows.push({
        name: name,
        address: (cells[COL_ADDRESS] || "").trim(),
        phone: normalizePhone(cells[COL_PHONE]),
        parsedPay: normalizePayToken(cells[COL_PAYMENT] || ""),
      });
    }
    return result;
  }

  // Python textwrap.wrap(text, width) davranışının karşılığı.
  const WS = "[\\t\\n\\v\\f\\r ]", NWS = "[^\\t\\n\\v\\f\\r ]";
  const W_ = "[\\p{L}\\p{M}\\p{N}_]", LT = "[\\p{L}\\p{M}_]", WP = "[\\p{L}\\p{M}\\p{N}_!\"'&.,?]";
  const WORDSEP_RE = new RegExp(
    `(${WS}+|(?<=${WP})-{2,}(?=${W_})|${NWS}+?(?:-(?:(?<=${LT}{2}-)|(?<=${LT}-${LT}-))(?=${LT}-?${LT})|(?=${WS}|$)|(?<=${WP})(?=-{2,}${W_})))`,
    "u"
  );

  function expandTabs(s, size) {
    let out = "", col = 0;
    for (const ch of s) {
      if (ch === "\t") { const n = size - (col % size); out += " ".repeat(n); col += n; }
      else { out += ch; col = ch === "\n" || ch === "\r" ? 0 : col + 1; }
    }
    return out;
  }

  function wrap(text, width) {
    text = expandTabs(String(text || ""), 8).replace(/[\t\n\v\f\r]/g, " ");
    const chunks = text.split(WORDSEP_RE).filter((c) => c);
    chunks.reverse();
    const lines = [];
    while (chunks.length) {
      const cur = [];
      let curLen = 0;
      if (lines.length && chunks[chunks.length - 1].trim() === "") chunks.pop();
      while (chunks.length) {
        const l = chunks[chunks.length - 1].length;
        if (curLen + l <= width) { cur.push(chunks.pop()); curLen += l; }
        else break;
      }
      if (chunks.length && chunks[chunks.length - 1].length > width && (width < 1 ? 1 : width - curLen) > 0) {
        const spaceLeft = width < 1 ? 1 : width - curLen;
        const chunk = chunks[chunks.length - 1];
        let end = spaceLeft;
        if (chunk.length > spaceLeft) {
          const hyphen = chunk.lastIndexOf("-", spaceLeft - 1);
          if (hyphen > 0 && /[^-]/.test(chunk.slice(0, hyphen))) end = hyphen + 1;
        }
        cur.push(chunk.slice(0, end));
        chunks[chunks.length - 1] = chunk.slice(end);
        if (chunks[chunks.length - 1] === "") chunks.pop();
        curLen += end;
      }
      if (cur.length && cur[cur.length - 1].trim() === "") cur.pop();
      if (cur.length) lines.push(cur.join(""));
    }
    return lines;
  }

  // ---------------------------------------------------------------------------
  // PDF (index.py > draw_label_on_canvas ile aynı ölçüler)
  // ReportLab'de orijin sol-alt, jsPDF'te sol-üst: y_js = H - y_rl
  // ---------------------------------------------------------------------------
  function getJsPDF() {
    if (typeof window !== "undefined" && window.jspdf) return window.jspdf.jsPDF;
    return require("jspdf").jsPDF; // Node (test)
  }

  function newDoc(pageName, assets) {
    const [W, H] = pageSize(pageName);
    const JsPDF = getJsPDF();
    const doc = new JsPDF({ unit: "pt", format: [W, H], orientation: "portrait", compress: true });
    let font = "Helvetica";
    if (assets && assets.fontBase64) {
      doc.addFileToVFS("DejaVuSans.ttf", assets.fontBase64);
      doc.addFont("DejaVuSans.ttf", "DejaVuSans", "normal");
      font = "DejaVuSans";
    }
    return { doc, W, H, font };
  }

  function drawLabel(ctx, opts, assets) {
    const { doc, W, H, font } = ctx;
    const name = opts.name || "", phone = opts.phone || "", address = opts.address || "";
    const sender = opts.sender || "", pay = opts.pay || "";
    const marginX = 10 * MM, marginY = 10 * MM;
    const usableW = W - 2 * marginX;
    const scale = Math.max(1.0, Math.min(2.0, Number(opts.badgeScale)));
    const txt = (s, x, yRl, o) => { if (s) doc.text(s, x, H - yRl, o); };

    // Ücret rozeti
    const badgeW = 30 * MM * scale, badgeH = 12 * MM * scale;
    doc.setFillColor(0.82 * 255, 0, 0);
    doc.roundedRect(W - marginX - badgeW, marginY, badgeW, badgeH, 3 * MM * scale, 3 * MM * scale, "F");
    doc.setTextColor(255, 255, 255);
    doc.setFont(font, "normal");
    doc.setFontSize(Math.trunc(26 * scale));
    txt(pay, W - marginX - badgeW / 2, H - marginY - badgeH / 2 - 3 * MM * scale, { align: "center" });
    doc.setTextColor(0, 0, 0);

    // Logo
    const topY = H - marginY - 4 * MM;
    let usedH = 0;
    if (assets && assets.logoBase64) {
      try {
        const targetW = 30 * MM;
        const targetH = assets.logoHeight * (targetW / assets.logoWidth);
        doc.addImage(assets.logoBase64, "PNG", marginX, H - topY, targetW, targetH, "kaffesa-logo");
        usedH = targetH;
      } catch (e) { usedH = 0; }
    }

    // Ayırıcı çizgi
    doc.setLineWidth(1.2);
    doc.setDrawColor(0, 0, 0);
    const lineY = H - marginY - (usedH + 6 * MM);
    doc.line(marginX, H - lineY, marginX + usableW, H - lineY);

    let y = H - marginY - (usedH + 16 * MM);
    doc.setFontSize(15); txt("ALICI", marginX, y); y -= 9 * MM;
    doc.setFontSize(28); txt(name, marginX, y); y -= 10 * MM;
    doc.setFontSize(18);
    const approxChars = Math.trunc(usableW / (3.7 * MM));
    for (const line of wrap(address, Math.max(45, approxChars))) { y -= 8 * MM; txt(line, marginX, y); }
    y -= 8 * MM; doc.setFontSize(16); txt("Tel: " + phone, marginX, y);
    y -= 12 * MM; doc.setFontSize(16); txt("Gönderici", marginX, y); y -= 8 * MM;
    doc.setFontSize(14);
    for (const line of sender.split("\n")) {
      if (line.trim()) { y -= 8 * MM; txt(line, marginX, y); }
    }
  }

  function buildSinglePdf(pageName, opts, assets) {
    const ctx = newDoc(pageName, assets);
    drawLabel(ctx, opts, assets);
    return ctx.doc;
  }

  function buildBulkPdf(pageName, rows, sender, badgeScale, assets) {
    const ctx = newDoc(pageName, assets);
    rows.forEach((r, i) => {
      if (i > 0) ctx.doc.addPage([ctx.W, ctx.H], "portrait");
      drawLabel(ctx, { name: r.name, phone: r.phone, address: r.address, sender, pay: r.finalPay || "", badgeScale }, assets);
    });
    return ctx.doc;
  }

  // ---------------------------------------------------------------------------
  // Tarayıcıdan yazdırma HTML'i (index.py > make_print_html / make_bulk_print_html)
  // ---------------------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function printCss(pageName, badgeScale) {
    let pageCss;
    if (pageName === "100x100") pageCss = "@page { size: 100mm 100mm; margin: 8mm; }";
    else if (pageName === "A4") pageCss = "@page { size: A4; margin: 10mm; }";
    else pageCss = "@page { size: A5; margin: 8mm; }";
    const fs = Math.trunc(22 * badgeScale), pv = Math.trunc(6 * badgeScale), ph = Math.trunc(14 * badgeScale);
    return pageCss +
      " body{font-family:Arial,sans-serif;margin:0;padding:0;-webkit-print-color-adjust:exact;print-color-adjust:exact;}" +
      ".frame{border:1px solid #000;padding:8mm;margin:8mm;position:relative;}" +
      `.pill{position:absolute;top:8mm;right:8mm;font-weight:800;font-size:${fs}px;color:#fff;background:#d00;padding:${pv}px ${ph}px;border-radius:10px;}` +
      ".head{display:flex;align-items:center;gap:8mm;margin-bottom:6mm;}" +
      ".sec{font-weight:700;margin-top:6mm;font-size:15px;}" +
      ".r-name{font-size:28px;font-weight:700;margin:4mm 0;}" +
      ".r-addr{font-size:18px;line-height:1.35;white-space:pre-wrap;}" +
      ".r-phone{font-size:16px;margin:2mm 0;}" +
      ".s-label{font-size:16px;margin-top:10mm;font-weight:700;}" +
      ".s-body{font-size:14px;white-space:pre-wrap;line-height:1.45;}" +
      ".page{page-break-after:always;}";
  }

  function labelHtml(r, sender, logoBase64, extraClass) {
    const logo = logoBase64
      ? `<img src="data:image/png;base64,${logoBase64}" style="height:auto; width:30mm; object-fit:contain; margin-right:8mm;" />`
      : "";
    return `<div class="frame${extraClass ? " " + extraClass : ""}"><div class="pill">${esc(r.pay)}</div>` +
      `<div class="head">${logo}</div><div class="sec">ALICI</div><div class="r-name">${esc(r.name)}</div>` +
      `<div class="r-addr">${esc(r.address)}</div><div class="r-phone">Tel: ${esc(r.phone)}</div>` +
      `<div class="s-label">Gönderici</div><div class="s-body">${esc(sender)}</div></div>`;
  }

  function makePrintHtml(pageName, labels, sender, badgeScale, logoBase64) {
    const bulk = labels.length > 1;
    const body = labels.map((r) => labelHtml(r, sender, logoBase64, bulk ? "page" : "")).join("");
    return `<!doctype html><html><head><meta charset="utf-8"><title>${bulk ? "Toplu Etiket Yazdır" : "Etiket"}</title>` +
      `<style>${printCss(pageName, badgeScale)}</style></head><body>${body}</body></html>`;
  }

  return {
    MM, COL_NAME, COL_ADDRESS, COL_PHONE, COL_PAYMENT, MIN_COLUMN_COUNT,
    ISTANBUL_INFO, ANKARA_INFO,
    normalizePayToken, normalizePhone, sanitizeFilename, pageSize, parseTSV, parseRecipients, wrap,
    buildSinglePdf, buildBulkPdf, makePrintHtml,
  };
});
