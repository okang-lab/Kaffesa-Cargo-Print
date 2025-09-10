# index.py
# requirements: streamlit, reportlab, pandas

import io, os, re, base64, textwrap
import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode import code128, qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

# -------------------------
# Genel Ayar
# -------------------------
st.set_page_config(page_title="Kargo Etiket Oluşturucu", layout="wide")

SENDER_BLOCK_DEFAULT = (
    "Kaffesa Ltd.\n"
    "Adres: ... Mah., ... Sk. No: ...\n"
    "İl/İlçe: İstanbul, Türkiye\n"
    "Tel: +90 5xx xxx xx xx\n"
)

# Türkçe karakter dostu font (aynı klasöre DejaVuSans.ttf koyarsan otomatik yüklenir)
FONT_NAME = "Helvetica"
if os.path.isfile("DejaVuSans.ttf"):
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))
        FONT_NAME = "DejaVuSans"
    except Exception:
        pass

# Sabit logo (index.py ile aynı klasörde logo.png)
def load_logo_bytes():
    try:
        with open("logo.png", "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None

# Ücret kısaltması normalize
def normalize_pay_token(token: str) -> str | None:
    if not token:
        return None
    t = token.strip().lower().replace("ü","ü").replace("ğ","g")
    if t in ("üa","ua"):
        return "ÜA"
    if t in ("üg","ug"):
        return "ÜG"
    return None

def sanitize_filename(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:60] if s else "etiket"

def wrap_text_lines(text: str, max_chars: int):
    for line in textwrap.wrap(text, width=max_chars):
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

def add_code128(c: canvas.Canvas, text, x, y, width_mm=32, height_mm=12):
    """
    Code128 barkodu doğrudan canvas'a çizer (drawOn).
    width_mm hedef genişlik; barWidth yaklaşık hesaplanır.
    """
    if not text:
        return
    # Yaklaşık modül sayısı: 11*len + sabitler
    approx_modules = 11 * len(text) + 35
    target_width_pt = width_mm * mm
    bar_width = max(min(target_width_pt / max(approx_modules, 1), 1.2), 0.2)
    bc = code128.Code128(
        text,
        barHeight=height_mm * mm,
        barWidth=bar_width,
        humanReadable=False
    )
    bc.drawOn(c, x, y)

def add_qr(c: canvas.Canvas, text, x, y, size_mm=28):
    if not text:
        return
    qrc = qr.QrCodeWidget(text)
    b = qrc.getBounds()
    w = b[2] - b[0]
    h = b[3] - b[1]
    d = Drawing(size_mm*mm, size_mm*mm)
    sx = (size_mm*mm) / w
    sy = (size_mm*mm) / h
    d.scale(sx, sy)
    d.add(qrc)
    renderPDF.draw(d, c, x, y)

# -------------------------
# PDF üretimi (A5 = yarım A4)
# -------------------------
def make_label_pdf(
    recipient_name, phone, address, sender_block, pay_short,
    page_size_name="A5",  # "A5" (yarım A4), "A4", "100x150"
    logo_bytes=None, order_id="", carrier="", put_qr=True, put_barcode=True
):
    # Sayfa boyutu
    if page_size_name == "100x150":
        W, H = 100*mm, 150*mm
    elif page_size_name == "A4":
        W, H = A4
    else:  # A5 (A4'ün yarısı)
        W, H = (148*mm, 210*mm)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))

    # Kenarlar
    margin_x = 10*mm
    margin_y = 10*mm
    usable_w = W - 2*margin_x

    # Kesim işaretleri
    draw_cut_marks(c, W, H)

    # Üst alan: Logo + Başlık + Ücret Rozeti
    c.setFillColorRGB(0.82, 0, 0)
    badge_w, badge_h = 30*mm, 12*mm
    c.roundRect(W - margin_x - badge_w, H - margin_y - badge_h, badge_w, badge_h, 3*mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(FONT_NAME, 26)
    c.drawCentredString(W - margin_x - badge_w/2, H - margin_y - badge_h/2 - 3, pay_short)
    c.setFillColorRGB(0, 0, 0)

    # Logo (solda)
    top_y = H - margin_y - 4*mm
    used_h = 0
    if logo_bytes:
        used_h = place_logo(c, logo_bytes, margin_x, top_y, width_mm=30)

    # Başlık
    c.setFont(FONT_NAME, 16)
    c.drawString(margin_x, H - margin_y - (used_h + 6*mm), "KARGO ETİKETİ")

    # Ayraç çizgi
    c.setLineWidth(1.2)
    c.line(margin_x, H - margin_y - (used_h + 10*mm), margin_x + usable_w, H - margin_y - (used_h + 10*mm))

    # ALICI — büyük puntolar
    y = H - margin_y - (used_h + 20*mm)
    c.setFont(FONT_NAME, 15)
    c.drawString(margin_x, y, "ALICI")
    y -= 9*mm

    c.setFont(FONT_NAME, 28)  # İsim/Firma büyük
    c.drawString(margin_x, y, f"{recipient_name}")
    y -= 10*mm

    c.setFont(FONT_NAME, 22)  # Telefon büyük
    c.drawString(margin_x, y, f"Tel: {phone}")
    y -= 9*mm

    # Adres — okunabilir büyük
    c.setFont(FONT_NAME, 16)
    approx_chars = int(usable_w / (3.7*mm))
    for line in wrap_text_lines(address, max(38, approx_chars)):
        y -= 7*mm
        c.drawString(margin_x, y, line)

    # (Opsiyonel) Kargo firması
    if carrier:
        y -= 8*mm
        c.setFont(FONT_NAME, 16)
        c.drawString(margin_x, y, f"Kargo: {carrier}")

    # QR & Barkod — sağ blok
    meta_text = (order_id or "").strip()
    right_x = W - margin_x - 34*mm
    top_block_y = H - margin_y - (used_h + 18*mm)
    if put_qr and meta_text:
        add_qr(c, f"{meta_text} | {pay_short}", right_x, top_block_y - 24*mm, size_mm=28)
    if put_barcode and meta_text:
        add_code128(c, meta_text, right_x, top_block_y - 42*mm, width_mm=32, height_mm=12)

    # GÖNDERİCİ — daha küçük puntolar
    y -= 14*mm
    c.setFont(FONT_NAME, 14)
    c.drawString(margin_x, y, "Gönderici")
    y -= 7*mm
    c.setFont(FONT_NAME, 12)
    for line in sender_block.split("\n"):
        if not line.strip():
            continue
        y -= 6*mm
        c.drawString(margin_x, y, line)

    # Dış çerçeve
    c.rect(margin_x-4*mm, margin_y, usable_w+8*mm, H - 2*margin_y)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue(), (W, H)

def make_print_html(recipient_name, phone, address, sender_block, pay_short,
                    page_size_name="A5", logo_b64=None, order_id="", carrier="", put_qr=True):
    # CSS boyut
    if page_size_name == "100x150":
        page_css = "@page { size: 100mm 150mm; margin: 8mm; }"
    elif page_size_name == "A4":
        page_css = "@page { size: A4; margin: 10mm; }"
    else:
        page_css = "@page { size: A5; margin: 8mm; }"

    logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height:auto; width:30mm; object-fit:contain; margin-right:8mm;" />' if logo_b64 else ""
    qr_html = f'<div style="font-size:11px;opacity:.7;">QR: {order_id} | {pay_short}</div>' if (put_qr and order_id) else ""

    html_block = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Etiket – {recipient_name}</title>
<style>
  {page_css}
  body {{ font-family: Arial, sans-serif; margin:0; padding:0; }}
  .frame {{ border: 1px solid #000; padding: 8mm; margin: 8mm; position: relative; }}
  .pill {{
    position: absolute; top: 8mm; right: 8mm;
    font-weight: 800; font-size: 22px; color: #fff; background: #d00;
    padding: 6px 14px; border-radius: 10px;
  }}
  .head {{ display:flex; align-items:center; gap:8mm; margin-bottom:6mm; }}
  .title {{ font-size: 16px; font-weight: 600; }}
  .sec {{ font-weight: 700; margin-top: 6mm; font-size: 15px; }}
  .r-name {{ font-size: 28px; font-weight: 700; margin: 4mm 0; }}
  .r-phone {{ font-size: 22px; margin: 2mm 0; }}
  .r-addr {{ font-size: 16px; line-height: 1.3; }}
  .s-label {{ font-size: 14px; margin-top: 8mm; font-weight: 700; }}
  .s-body {{ font-size: 12px; white-space: pre-wrap; }}
  @media print {{ a#print-btn {{ display:none; }} }}
</style>
</head>
<body>
  <div class="frame">
    <div class="pill">{pay_short}</div>
    <div class="head">{logo_html}<div class="title">KARGO ETİKETİ</div></div>

    <div class="sec">ALICI</div>
    <div class="r-name">{recipient_name}</div>
    <div class="r-phone">Tel: {phone}</div>
    {"<div class='r-addr'>Kargo: "+carrier+"</div>" if carrier else ""}
    <div class="r-addr">{address}</div>

    <div class="s-label">Gönderici</div>
    <div class="s-body">{sender_block}</div>

    <div style="margin-top:6mm;font-size:11px;opacity:.8;">Sipariş No: {order_id}</div>
    {qr_html}
  </div>
  <a id="print-btn" href="#" onclick="window.print();return false;"
     style="display:block;text-align:center;margin:10px 8mm;padding:.6rem;border:1px solid #ddd;border-radius:8px;text-decoration:none;">
     🖨️ Yazdır
  </a>
</body>
</html>
"""
    return "data:text/html;base64," + base64.b64encode(html_block.encode("utf-8")).decode("ascii")

# -------------------------
# UI
# -------------------------
st.title("Kargo Etiket Oluşturucu")

with st.sidebar:
    st.subheader("Alıcı Bilgileri (kopyala–yapıştır)")
    st.caption("Sütun: İsim/Firma | Telefon | Adres | (ops) ÜA/ÜG | (ops) Sipariş No | (ops) Kargo")
    raw = st.text_area(
        "Her satır bir alıcıyı temsil eder. Sütunları ; / , / TAB ile ayır.",
        height=220,
        placeholder="Ör:\nAcme A.Ş.; 0532 000 00 00; Cumhuriyet Cad. No:12 Şişli İstanbul; ÜA; SIP12345; Aras\nBurcu Girer, 0505 111 22 33, ...; ÜG",
    )
    sep = st.radio("Ayraç", [",", ";", "TAB"], horizontal=True)
    sep_char = "\t" if sep == "TAB" else sep

st.markdown(
    "- **Yarım A4 (A5)** varsayılan: A4’ün yarısı kadar yer kaplar, uzaktan okunur büyük yazı.\n"
    "- Metin kutusundaki **ÜA/ÜG** dördüncü sütundan okunur; **radyo seçimi** nihai karardır."
)

with st.expander("🔧 Tasarım & Seçenekler"):
    colA, colB = st.columns(2)
    with colA:
        page_size_name = st.selectbox("Etiket Boyutu", ["A5", "A4", "100x150"], index=0)
        sender_block = st.text_area("Gönderici Bloğu", value=SENDER_BLOCK_DEFAULT, height=120)
    with colB:
        put_qr = st.checkbox("QR kod ekle (Sipariş No varsa)", value=True)
        put_barcode = st.checkbox("Barkod (Code128) ekle", value=True)
        st.caption("QR/Barkod için satırdaki 5. sütun 'Sipariş No' kullanılır.")

# Satırları parse et
rows = []
for line in raw.splitlines():
    if not line.strip():
        continue
    parts = [p.strip() for p in line.split(sep_char)]
    parts = [p for p in parts if p != ""]
    if len(parts) >= 3:
        parsed_pay = normalize_pay_token(parts[3]) if len(parts) >= 4 else None
        rows.append(
            {
                "name": parts[0],
                "phone": parts[1],
                "address": parts[2],
                "parsed_pay": parsed_pay,
                "order_id": parts[4] if len(parts) >= 5 else "",
                "carrier":  parts[5] if len(parts) >= 6 else "",
            }
        )

if not rows:
    st.info("Sağda butonların gelmesi için soldaki kutuya en az 1 satır alıcı bilgisi gir.")
else:
    st.success(f"{len(rows)} alıcı bulundu. Her biri için **ÜA/ÜG** son kontrol ve tek sayfa PDF butonu aşağıda.")

    logo_bytes = load_logo_bytes()
    logo_b64 = base64.b64encode(logo_bytes).decode("ascii") if logo_bytes else None

    for i, r in enumerate(rows, start=1):
        with st.container(border=True):
            st.markdown(f"**#{i} – {r['name']}**")
            st.write(f"**Telefon:** {r['phone']}")
            st.write(f"**Adres:** {r['address']}")
            if r.get("carrier"):
                st.write(f"**Kargo:** {r['carrier']}")
            if r.get("order_id"):
                st.write(f"**Sipariş No:** {r['order_id']}")

            # Radyo varsayılanı: satırdan geldiyse onu seç
            default_index = 0  # ÜA
            if r.get("parsed_pay") == "ÜG":
                default_index = 1
            pay_opt = st.radio(
                "Kargo ücreti",
                ["ÜA (Ücret Alıcı)", "ÜG (Ücret Gönderici)"],
                index=default_index,
                horizontal=True,
                key=f"pay_{i}"
            )
            pay_short = "ÜA" if "ÜA" in pay_opt else "ÜG"

            col1, col2 = st.columns([1,1])

            # 1) PDF indir
            with col1:
                pdf_bytes, _ = make_label_pdf(
                    r["name"], r["phone"], r["address"],
                    sender_block, pay_short,
                    page_size_name=page_size_name,
                    logo_bytes=logo_bytes,
                    order_id=r.get("order_id",""),
                    carrier=r.get("carrier",""),
                    put_qr=put_qr, put_barcode=put_barcode
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

            # 2) Tarayıcıdan yazdır
            with col2:
                data_url = make_print_html(
                    r["name"], r["phone"], r["address"], sender_block, pay_short,
                    page_size_name=page_size_name,
                    logo_b64=logo_b64, order_id=r.get("order_id",""),
                    carrier=r.get("carrier",""), put_qr=put_qr
                )
                st.markdown(
                    f'<a href="{data_url}" target="_blank" '
                    'style="display:block;text-align:center;padding:.6rem;border:1px solid #ddd;'
                    'border-radius:8px;text-decoration:none;">🖨️ Tarayıcıdan yazdır (tek sayfa)</a>',
                    unsafe_allow_html=True,
                )
