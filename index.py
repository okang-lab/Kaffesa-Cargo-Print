# index.py
# requirements: streamlit, reportlab, pandas

import io, os, re, base64, textwrap, unicodedata
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# -------------------------
# Genel Ayar
# -------------------------
st.set_page_config(page_title="Kargo Etiket Oluşturucu", layout="wide")

SENDER_BLOCK_DEFAULT = (
    "KAFFESA GIDA SANAYİ VE DIŞ TİCARET ANONİM ŞİRKETİ\n"
    "Adres: BALMUMCU MAH. BARBAROS BULVARI İBA BLOKLARI, 34/A\n"
    "İl/İlçe: Beşiktaş/İstanbul\n"
    "Tel: 0212 265 16 16\n"
)

# Türkçe karakter dostu font (aynı klasöre DejaVuSans.ttf koy)
FONT_PATH = "DejaVuSans.ttf"
if os.path.isfile(FONT_PATH):
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
    FONT_NAME = "DejaVuSans"
else:
    FONT_NAME = "Helvetica"
    st.error("⚠️ DejaVuSans.ttf bulunamadı. PDF’te Türkçe ve satır aralıkları bozulabilir. "
             "Lütfen dosyayı proje köküne ekleyin.")

# Sabit logo (index.py ile aynı klasörde logo.png)
def load_logo_bytes():
    try:
        with open("logo.png", "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None

# Ücret kısaltması normalize (ÜA/ÜG)
def normalize_pay_token(token: str) -> str | None:
    if not token:
        return None
    t = unicodedata.normalize("NFKC", token).strip().lower().replace(" ", "")
    if t in ("üa", "ua"): return "ÜA"
    if t in ("üg", "ug"): return "ÜG"
    return None

def sanitize_filename(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:60] if s else "etiket"

def wrap_text_lines(text: str, max_chars: int):
    for line in textwrap.wrap(text or "", width=max_chars):
        yield line

def draw_cut_marks(c: canvas.Canvas, W, H, margin=6*mm, len_=5*mm):
    c.setLineWidth(0.8)
    # Sol üst
    c.line(margin, H-margin, margin+len_, H-margin)
    c.line(margin, H-margin, margin, H-margin-len_)
    # Sağ üst
    c.line(W-margin-len_, H-margin, W-margin, H-margin)
    c.line(W-margin, H-margin, W-margin, H-margin-len_)
    # Sol alt
    c.line(margin, margin, margin+len_, margin)
    c.line(margin, margin, margin, margin+len_)
    # Sağ alt
    c.line(W-margin-len_, margin, W-margin, margin)
    c.line(W-margin, margin, W-margin, margin+len_)

def place_logo(c: canvas.Canvas, logo_bytes, x, y, width_mm):
    try:
        img = ImageReader(io.BytesIO(logo_bytes))
        iw, ih = img.getSize()
        target_w = width_mm * mm
        scale = target_w / iw
        target_h = ih * scale
        c.drawImage(img, x, y - target_h, width=target_w, height=target_h, mask='auto')
        return target_h
    except Exception:
        return 0

# --- Sayfa boyutu helper ---
def get_pagesize(name="A4"):
    if name == "100x150":
        return (100*mm, 150*mm)
    elif name == "A4":
        return A4
    else:
        return (148*mm, 210*mm)  # A5 (yarım A4)

# -------------------------
# Yazdırmayı yeni pencerede güvenli tetikleme
# -------------------------
def open_print_window_with_html(html: str):
    """
    Yazdırma içeriğini yeni sekmeye yazar ve güvenli şekilde print eder.
    """
    safe_js = f"""
    <script>
    (function() {{
      try {{
        var w = window.open('', '_blank');
        if (!w) {{
          alert('Tarayıcı yeni pencere açmayı engelledi. Lütfen bu site için pop-up izni verin.');
          return;
        }}
        w.document.open();
        w.document.write(`{html.replace('`','\\`')}`);
        w.document.close();

        var imgs = w.document.images;
        var total = imgs.length, loaded = 0;
        function done() {{
          try {{ w.focus(); setTimeout(function(){{ w.print(); }}, 120); }} catch(e) {{}}
        }}
        if (total === 0) {{ done(); }}
        else {{
          for (var i=0;i<total;i++) {{
            if (imgs[i].complete) {{
              loaded++; if (loaded===total) done();
            }} else {{
              imgs[i].addEventListener('load', function(){{ loaded++; if (loaded===total) done(); }});
              imgs[i].addEventListener('error', function(){{ loaded++; if (loaded===total) done(); }});
            }}
          }}
        }}
      }} catch (e) {{
        alert('Yazdırma penceresi açılamadı: ' + e);
      }}
    }})();
    </script>
    """
    components.html(safe_js, height=0, scrolling=False)

# -------------------------
# ÇİZİM: Etiketi varolan canvas’a çiz (PDF)
# -------------------------
def draw_label_on_canvas(
    c: canvas.Canvas, W, H,
    recipient_name, phone, address, sender_block, pay_short,
    logo_bytes=None, badge_scale=1.7
):
    margin_x = 10*mm
    margin_y = 10*mm
    usable_w = W - 2*margin_x

    # Kesim işaretleri
    draw_cut_marks(c, W, H)

    # Ücret rozeti (kırmızı) — 1×–2× ölçek
    scale = max(1.0, min(2.0, float(badge_scale)))
    c.setFillColorRGB(0.82, 0, 0)
    badge_w, badge_h = 30*mm*scale, 12*mm*scale
    c.roundRect(W - margin_x - badge_w, H - margin_y - badge_h, badge_w, badge_h, 3*mm*scale, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(FONT_NAME, int(26*scale))
    c.drawCentredString(W - margin_x - badge_w/2, H - margin_y - badge_h/2 - (3*scale), pay_short)
    c.setFillColorRGB(0, 0, 0)

    # Logo (solda)
    top_y = H - margin_y - 4*mm
    used_h = 0
    if logo_bytes:
        used_h = place_logo(c, logo_bytes, margin_x, top_y, width_mm=30)

    # Ayraç çizgi
    c.setLineWidth(1.2)
    c.line(margin_x, H - margin_y - (used_h + 6*mm), margin_x + usable_w, H - margin_y - (used_h + 6*mm))

    # ALICI — büyük puntolar
    y = H - margin_y - (used_h + 16*mm)
    c.setFont(FONT_NAME, 15)
    c.drawString(margin_x, y, "ALICI")
    y -= 9*mm

    c.setFont(FONT_NAME, 28)  # Alıcı adı / firma
    c.drawString(margin_x, y, f"{recipient_name}")
    y -= 10*mm

    # ÖNCE ADRES (büyük kısa satır + tam adres daha büyük)
    addr_short = (address or "").replace("\n", " ").strip()
    if len(addr_short) > 60:
        addr_short = addr_short[:60] + "…"
    c.setFont(FONT_NAME, 22)  # kısa satır (büyük)
    c.drawString(margin_x, y, f"Adres: {addr_short}")
    y -= 9*mm

    c.setFont(FONT_NAME, 18)  # tam adres (telefon'dan daha büyük)
    approx_chars = int(usable_w / (3.7*mm))
    for line in wrap_text_lines(address, max(38, approx_chars)):
        y -= 8*mm
        c.drawString(margin_x, y, line)

    # SONRA TELEFON (daha küçük)
    y -= 8*mm
    c.setFont(FONT_NAME, 16)
    c.drawString(margin_x, y, f"Tel: {phone}")
    y -= 8*mm

    # GÖNDERİCİ — büyük ve ferah
    y -= 12*mm
    c.setFont(FONT_NAME, 16)   # başlık
    c.drawString(margin_x, y, "Gönderici")
    y -= 8*mm
    c.setFont(FONT_NAME, 14)   # gövde
    for line in (sender_block or "").split("\n"):
        if not line.strip():
            continue
        y -= 8*mm
        c.drawString(margin_x, y, line)

    # Dış çerçeve
    c.rect(margin_x-4*mm, margin_y, usable_w+8*mm, H - 2*margin_y)

# -------------------------
# TEK ETİKET PDF (indir)
# -------------------------
def build_single_label_pdf(page_size_name, **kwargs):
    W, H = get_pagesize(page_size_name)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    draw_label_on_canvas(c, W, H, **kwargs)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

# -------------------------
# TOPLU PDF (çok sayfa, indir)
# -------------------------
def build_bulk_pdf(page_size_name, rows, sender_block, logo_bytes, badge_scale):
    W, H = get_pagesize(page_size_name)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    for r in rows:
        pay_short = r["final_pay"]
        draw_label_on_canvas(
            c, W, H,
            r["name"], r["phone"], r["address"],
            sender_block, pay_short,
            logo_bytes=logo_bytes,
            badge_scale=badge_scale
        )
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

# -------------------------
# HTML yazdırma (tek) — string döner
# -------------------------
def make_print_html(recipient_name, phone, address, sender_block, pay_short,
                    page_size_name="A4", logo_b64=None, badge_scale=1.7):
    if page_size_name == "100x150":
        page_css = "@page { size: 100mm 150mm; margin: 8mm; }"
    elif page_size_name == "A4":
        page_css = "@page { size: A4; margin: 10mm; }"
    else:
        page_css = "@page { size: A5; margin: 8mm; }"

    pill_fs = int(22*badge_scale)
    pill_pad_v = int(6*badge_scale)
    pill_pad_h = int(14*badge_scale)
    logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height:auto; width:30mm; object-fit:contain; margin-right:8mm;" />' if logo_b64 else ""

    addr_short = (address or "").replace("\n", " ").strip()
    if len(addr_short) > 60:
        addr_short = addr_short[:60] + "…"

    html_block = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Etiket</title>
<style>
  {page_css}
  body {{ font-family: Arial, sans-serif; margin:0; padding:0;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .frame {{ border: 1px solid #000; padding: 8mm; margin: 8mm; position: relative; }}
  .pill {{
    position: absolute; top: 8mm; right: 8mm;
    font-weight: 800; font-size: {pill_fs}px; color: #fff; background: #d00;
    padding: {pill_pad_v}px {pill_pad_h}px; border-radius: 10px;
  }}
  .head {{ display:flex; align-items:center; gap:8mm; margin-bottom:6mm; }}
  .sec {{ font-weight: 700; margin-top: 6mm; font-size: 15px; }}
  .r-name {{ font-size: 28px; font-weight: 700; margin: 4mm 0; }}
  .r-addr-big {{ font-size: 22px; margin: 2mm 0; }}   /* kısa adres */
  .r-addr {{ font-size: 18px; line-height: 1.35; }}  /* tam adres (telefon'dan büyük) */
  .r-phone {{ font-size: 16px; margin: 2mm 0; }}     /* telefon (küçük) */
  .s-label {{ font-size: 16px; margin-top: 10mm; font-weight: 700; }}
  .s-body {{ font-size: 14px; white-space: pre-wrap; line-height: 1.45; }}
  @media print {{ a#print-btn {{ display:none; }} }}
</style>
</head>
<body>
  <div class="frame">
    <div class="pill">{pay_short}</div>
    <div class="head">{logo_html}</div>

    <div class="sec">ALICI</div>
    <div class="r-name">{recipient_name}</div>
    <div class="r-addr-big">Adres: {addr_short}</div>
    <div class="r-addr">{address}</div>
    <div class="r-phone">Tel: {phone}</div>

    <div class="s-label">Gönderici</div>
    <div class="s-body">{sender_block}</div>
  </div>
</body>
</html>
"""
    return html_block

# -------------------------
# HTML toplu yazdırma (çok sayfa) — string döner
# -------------------------
def make_bulk_print_html(page_size_name, rows, sender_block, logo_b64, badge_scale=1.7):
    if page_size_name == "100x150":
        page_css = "@page { size: 100mm 150mm; margin: 8mm; }"
    elif page_size_name == "A4":
        page_css = "@page { size: A4; margin: 10mm; }"
    else:
        page_css = "@page { size: A5; margin: 8mm; }"

    pill_fs = int(22*badge_scale)
    pill_pad_v = int(6*badge_scale)
    pill_pad_h = int(14*badge_scale)

    pages = []
    for r in rows:
        addr_short = (r['address'] or "").replace("\n", " ").strip()
        if len(addr_short) > 60:
            addr_short = addr_short[:60] + "…"
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height:auto; width:30mm; object-fit:contain; margin-right:8mm;" />' if logo_b64 else ""

        page = f"""
<div class="frame page">
  <div class="pill">{r['final_pay']}</div>
  <div class="head">{logo_html}</div>

  <div class="sec">ALICI</div>
  <div class="r-name">{r['name']}</div>
  <div class="r-addr-big">Adres: {addr_short}</div>
  <div class="r-addr">{r['address']}</div>
  <div class="r-phone">Tel: {r['phone']}</div>

  <div class="s-label">Gönderici</div>
  <div class="s-body">{sender_block}</div>
</div>
"""
        pages.append(page)

    html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Toplu Etiket Yazdır</title>
<style>
  {page_css}
  body {{ font-family: Arial, sans-serif; margin:0; padding:0;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .frame {{ border: 1px solid #000; padding: 8mm; margin: 8mm; position: relative; }}
  .pill {{
    position: absolute; top: 8mm; right: 8mm;
    font-weight: 800; font-size: {pill_fs}px; color: #fff; background: #d00;
    padding: {pill_pad_v}px {pill_pad_h}px; border-radius: 10px;
  }}
  .head {{ display:flex; align-items:center; gap:8mm; margin-bottom:6mm; }}
  .sec {{ font-weight: 700; margin-top: 6mm; font-size: 15px; }}
  .r-name {{ font-size: 28px; font-weight: 700; margin: 4mm 0; }}
  .r-addr-big {{ font-size: 22px; margin: 2mm 0; }}
  .r-addr {{ font-size: 18px; line-height: 1.35; }}
  .r-phone {{ font-size: 16px; margin: 2mm 0; }}
  .s-label {{ font-size: 16px; margin-top: 10mm; font-weight: 700; }}
  .s-body {{ font-size: 14px; white-space: pre-wrap; line-height: 1.45; }}
  .page {{ page-break-after: always; }}
</style>
</head>
<body>
  {''.join(pages)}
</body>
</html>
"""
    return html

# -------------------------
# UI
# -------------------------
st.title("Kargo Etiket Oluşturucu")

with st.sidebar:
    st.subheader("Alıcı Bilgileri (Excel’den kopyala–yapıştır)")
    st.caption("Bu modda 19 sütundan **I=Alıcı Adı (9)**, **Q=Adres (17)**, **R=Telefon (18)**, **S=Kargo Ödemesi (ÜA/ÜG) (19)** okunur.")
    raw = st.text_area(
        "Excel’den satırları kopyalayıp buraya yapıştır. Ayraç genelde TAB olur.",
        height=240,
        placeholder="Excel satırlarını (19 sütun) kopyalayıp yapıştırın. I/Q/R/S otomatik alınır.",
    )
    sep = st.radio("Ayraç", ["TAB", ";", ","], index=0, horizontal=True)
    sep_char = "\t" if sep == "TAB" else (";" if sep == ";" else ",")

st.markdown(
    "- **Varsayılan Boyut:** A4 (menüden A5 ya da 100×150 seçebilirsin).\n"
    "- **Excel Modu (güncel):** I=Ad, Q=Adres, R=Telefon, S=ÜA/ÜG.\n"
    "- **Güvenli Yazdır:** Yazdırma penceresi yeni sekmede güvenle açılır."
)

with st.expander("🔧 Tasarım & Seçenekler"):
    colA, colB = st.columns(2)
    with colA:
        page_size_name = st.selectbox("Etiket Boyutu", ["A5", "A4", "100x150"], index=1)  # A4 default
        sender_block = st.text_area("Gönderici Bloğu", value=SENDER_BLOCK_DEFAULT, height=140)
    with colB:
        badge_scale = st.slider("Ücret rozeti ölçeği (1×–2×)", 1.0, 2.0, 1.7, 0.1)

# -------------------------
# Satırları parse et — I, Q, R, S  (I=9, Q=17, R=18, S=19)
# -------------------------
rows = []
for line in raw.splitlines():
    if not line.strip():
        continue
    parts = [p.strip() for p in line.split(sep_char)]
    if len(parts) < 19:
        parts += [""] * (19 - len(parts))

    name_cell  = parts[8]   # I (9)  -> Alıcı Adı
    addr_cell  = parts[16]  # Q (17) -> Adres
    phone_cell = parts[17]  # R (18) -> Telefon
    pay_cell   = parts[18]  # S (19) -> Ücret (ÜA/ÜG)

    parsed_pay = normalize_pay_token(pay_cell) if pay_cell else None

    if any([name_cell, phone_cell, addr_cell, parsed_pay]):
        rows.append(
            {
                "name": name_cell,
                "phone": phone_cell,
                "address": addr_cell,
                "parsed_pay": parsed_pay,
            }
        )

if not rows:
    st.info("Sağda butonların gelmesi için soldaki kutuya Excel’den en az 1 satır yapıştır.")
else:
    st.success(f"{len(rows)} alıcı bulundu. Kargo ödemesi (ÜA/ÜG) için son kontrol yapıp yazdır/indir.")

    logo_bytes = load_logo_bytes()
    logo_b64 = base64.b64encode(logo_bytes).decode("ascii") if logo_bytes else None

    # --- Kartlarda son kontrol + tekli butonlar ---
    for i, r in enumerate(rows, start=1):
        with st.container(border=True):
            st.markdown(f"**#{i} – {r['name']}**")
            if r.get("address"): st.write(f"**Adres:** {r['address']}")
            if r.get("phone"):   st.write(f"**Telefon:** {r['phone']}")

            # Radyo varsayılanı: satırdan geldiyse onu seç
            default_index = 0  # ÜA
            if r.get("parsed_pay") == "ÜG":
                default_index = 1
            pay_opt = st.radio(
                "Kargo ödemesi",
                ["ÜA (Ücret Alıcı)", "ÜG (Ücret Gönderici)"],
                index=default_index,
                horizontal=True,
                key=f"pay_{i}"
            )
            pay_short = "ÜA" if "ÜA" in pay_opt else "ÜG"
            rows[i-1]["final_pay"] = pay_short

            col1, col2 = st.columns([1,1])

            # 1) Tek PDF indir
            with col1:
                pdf_bytes = build_single_label_pdf(
                    page_size_name,
                    recipient_name=r["name"], phone=r["phone"], address=r["address"],
                    sender_block=sender_block, pay_short=pay_short,
                    logo_bytes=logo_bytes, badge_scale=badge_scale
                )
                file_name = f"etiket_{sanitize_filename(r['name'])}.pdf"
                st.download_button(
                    label="📄 PDF indir (tek sayfa)",
                    data=pdf_bytes,
                    file_name=file_name,
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_{i}",
                )

            # 2) Tek yazdır (güvenli yeni pencere)
            with col2:
                if st.button("🖨️ Tarayıcıdan yazdır (tek sayfa)", key=f"print_{i}", use_container_width=True):
                    html = make_print_html(
                        r["name"], r["phone"], r["address"], sender_block, pay_short,
                        page_size_name=page_size_name, logo_b64=logo_b64, badge_scale=badge_scale
                    )
                    open_print_window_with_html(html)

    # --- Toplu işlemler ---
    st.markdown("### Toplu işlemler")
    colA, colB = st.columns([1,1])

    with colA:
        bulk_pdf = build_bulk_pdf(page_size_name, rows, sender_block, logo_bytes, badge_scale)
        st.download_button(
            label="📦 Toplu PDF indir (çok sayfa)",
            data=bulk_pdf,
            file_name="etiketler_toplu.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="bulk_pdf_dl",
        )

    with colB:
        if st.button("🖨️ Toplu yazdır (tarayıcı)", use_container_width=True):
            bulk_html = make_bulk_print_html(page_size_name, rows, sender_block, logo_b64, badge_scale)
            open_print_window_with_html(bulk_html)
