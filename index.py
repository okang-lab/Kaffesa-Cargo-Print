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
    "KAFFESA GIDA SANAYİ VE DIŞ TİCARET ANONİM ŞİRKETİ\n"
    "Adres: BALMUMCU MAH. BARBAROS BULVARI İBA BLOKLARI, 34/A\n"
    "İl/İlçe: Beşiktaş/İstanbul\n"
    "Tel: 0212 265 16 16\n"
)

# Türkçe karakter dostu font (aynı klasöre DejaVuSans.ttf koy)
FONT_NAME = None
FONT_PATH = "DejaVuSans.ttf"
if os.path.isfile(FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
        FONT_NAME = "DejaVuSans"
    except Exception as e:
        FONT_NAME = "Helvetica"  # son çare
else:
    FONT_NAME = "Helvetica"

if FONT_NAME != "DejaVuSans":
    st.warning("Türkçe karakterlerin PDF’te bozulmaması için **DejaVuSans.ttf** dosyasını proje köküne ekleyin.")

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
    # birleşik 'ü' gibi varyasyonları normalize et
    t = (token.strip()
               .lower()
               .replace("ü", "ü")
               .replace("ğ", "g"))
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
    """Code128 barkodu doğrudan canvas'a çizer (drawOn)."""
    if not text:
        return
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
    w = b[2] - b[0]; h = b[3] - b[1]
    d = Drawing(size_mm*mm, size_mm*mm)
    sx = (size_mm*mm) / w; sy = (size_mm*mm) / h
    d.scale(sx, sy)
    d.add(qrc)
    renderPDF.draw(d, c, x, y)

# --- Sayfa boyutu helper ---
def get_pagesize(name="A5"):
    if name == "100x150":
        return (100*mm, 150*mm)
    elif name == "A4":
        return A4
    else:
        return (148*mm, 210*mm)  # A5

# -------------------------
# ÇİZİM: Etiketi varolan canvas’a çiz
# -------------------------
def draw_label_on_canvas(
    c: canvas.Canvas, W, H,
    recipient_name, phone, address, sender_block, pay_short,
    logo_bytes=None, order_id="", carrier="", put_qr=True, put_barcode=True
):
    margin_x = 10*mm
    margin_y = 10*mm
    usable_w = W - 2*margin_x

    # Kesim işaretleri
    draw_cut_marks(c, W, H)

    # Ücret rozeti (büyük ve kırmızı)
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

    # Başlık YOK (kaldırıldı)

    # Ayraç çizgi
    c.setLineWidth(1.2)
    c.line(margin_x, H - margin_y - (used_h + 6*mm), margin_x + usable_w, H - margin_y - (used_h + 6*mm))

    # ALICI — büyük puntolar
    y = H - margin_y - (used_h + 16*mm)
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
    top_block_y = H - margin_y - (used_h + 14*mm)
    if put_qr and meta_text:
        add_qr(c, f"{meta_text} | {pay_short}", right_x, top_block_y - 24*mm, size_mm=28)
    if put_barcode and meta_text:
        add_code128(c, meta_text, right_x, top_block_y - 42*mm, width_mm=32, height_mm=12)

    # GÖNDERİCİ — daha küçük
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
def build_bulk_pdf(page_size_name, rows, sender_block, logo_bytes, put_qr, put_barcode):
    W, H = get_pagesize(page_size_name)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    for r in rows:
        pay_short = r["final_pay"]  # önceden hesaplanacak
        draw_label_on_canvas(
            c, W, H,
            r["name"], r["phone"], r["address"],
            sender_block, pay_short,
            logo_bytes=logo_bytes,
            order_id=r.get("order_id",""),
            carrier=r.get("carrier",""),
            put_qr=put_qr, put_barcode=put_barcode
        )
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

# -------------------------
# HTML yazdırma (tek)
# -------------------------
def make_print_html(recipient_name, phone, address, sender_block, pay_short,
                    page_size_name="A5", logo_b64=None, order_id="", carrier="", put_qr=True):
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
<title>Etiket</title>
<style>
  {page_css}
  body {{ font-family: Arial, sans-serif; margin:0; padding:0;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .frame {{ border: 1px solid #000; padding: 8mm; margin: 8mm; position: relative; }}
  .pill {{
    position: absolute; top: 8mm; right: 8mm;
    font-weight: 800; font-size: 22px; color: #fff; background: #d00;
    padding: 6px 14px; border-radius: 10px;
  }}
  .head {{ display:flex; align-items:center; gap:8mm; margin-bottom:6mm; }}
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
    <div class="head">{logo_html}</div>

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
# HTML toplu yazdırma (çok sayfa)
# -------------------------
def make_bulk_print_html(page_size_name, rows, sender_block, logo_b64, put_qr):
    if page_size_name == "100x150":
        page_css = "@page { size: 100mm 150mm; margin: 8mm; }"
    elif page_size_name == "A4":
        page_css = "@page { size: A4; margin: 10mm; }"
    else:
        page_css = "@page { size: A5; margin: 8mm; }"

    pages = []
    for r in rows:
        pay_short = r["final_pay"]
        qr_html = f'<div style="font-size:11px;opacity:.7;">QR: {r.get("order_id","")} | {pay_short}</div>' if (put_qr and r.get("order_id")) else ""
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height:auto; width:30mm; object-fit:contain; margin-right:8mm;" />' if logo_b64 else ""

        page = f"""
<div class="frame page">
  <div class="pill">{pay_short}</div>
  <div class="head">{logo_html}</div>

  <div class="sec">ALICI</div>
  <div class="r-name">{r['name']}</div>
  <div class="r-phone">Tel: {r['phone']}</div>
  {"<div class='r-addr'>Kargo: "+r.get("carrier","")+"</div>" if r.get("carrier") else ""}
  <div class="r-addr">{r['address']}</div>

  <div class="s-label">Gönderici</div>
  <div class="s-body">{sender_block}</div>

  <div style="margin-top:6mm;font-size:11px;opacity:.8;">Sipariş No: {r.get("order_id","")}</div>
  {qr_html}
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
    font-weight: 800; font-size: 22px; color: #fff; background: #d00;
   """
    return ...
