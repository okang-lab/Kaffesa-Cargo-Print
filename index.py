# index.py
# requirements: streamlit, reportlab, pandas

import io
import re
import base64
import textwrap
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

st.set_page_config(page_title="Kaffesa Kargo Etiket Oluşturucu by okanLab", layout="wide")

SENDER_BLOCK = (
    "KAFFESA GIDA SANAYİ VE DIŞ TİCARET ANONİM ŞİRKETİ"
    "Adres:BALMUMCU MAH. BARBAROS BULVARI İBA BLOKLARI , 34\A"
    "İl/İlçe: İstanbul, Türkiye\n"
    "Tel: ‭0 (212) 265 16 16‬"
)

def sanitize_filename(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:60] if s else "etiket"

def wrap_text_lines(text: str, max_chars: int):
    for line in textwrap.wrap(text, width=max_chars):
        yield line

def make_label_pdf(recipient_name, phone, address, sender_block, pay_short):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    margin_x = 15 * mm
    margin_y = 15 * mm
    usable_w = W - 2 * margin_x

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin_x, H - margin_y, "KARGO ETİKETİ")

    c.setFillColorRGB(1, 0, 0)
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(W - margin_x, H - margin_y, pay_short)
    c.setFillColorRGB(0, 0, 0)

    c.setLineWidth(1)
    c.line(margin_x, H - margin_y - 5*mm, margin_x + usable_w, H - margin_y - 5*mm)

    y = H - margin_y - 15*mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin_x, y, "Alıcı")
    y -= 7*mm
    c.setFont("Helvetica", 12)
    c.drawString(margin_x, y, f"İsim/Firma : {recipient_name}")
    y -= 6*mm
    c.drawString(margin_x, y, f"Telefon     : {phone}")
    y -= 6*mm

    for line in wrap_text_lines(address, max_chars=int((W - 2*margin_x) / (3.5*mm))):
        y -= 6*mm
        c.drawString(margin_x, y, line)

    y -= 14*mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin_x, y, "Gönderici")
    y -= 7*mm
    c.setFont("Helvetica", 12)
    for line in sender_block.split("\n"):
        if not line.strip():
            continue
        y -= 6*mm
        c.drawString(margin_x, y, line)

    c.rect(margin_x-5*mm, margin_y, usable_w+10*mm, H - 2*margin_y)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

def make_print_html(recipient_name, phone, address, sender_block, pay_short):
    html_block = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Etiket – {recipient_name}</title>
<style>
  @page {{ size: A4; margin: 12mm; }}
  body {{ font-family: Arial, sans-serif; margin:0; padding:0; }}
  .frame {{ border: 1px solid #000; padding: 10mm; margin: 8mm; position: relative; }}
  h1 {{ font-size: 18px; margin: 0 0 8mm 0; }}
  .sec-title {{ font-weight: 700; margin-top: 6mm; }}
  .line {{ margin: 2mm 0; }}
  .badge {{
    position: absolute;
    top: 8mm;
    right: 10mm;
    font-weight: 800;
    font-size: 24px;
    color: #fff;
    background: #d00;
    padding: 4px 10px;
    border-radius: 8px;
  }}
  @media print {{ a#print-btn {{ display:none; }} }}
</style>
</head>
<body>
  <div class="frame">
    <div class="badge">{pay_short}</div>
    <h1>KARGO ETİKETİ</h1>
    <div class="sec-title">Alıcı</div>
    <div class="line">İsim/Firma: {recipient_name}</div>
    <div class="line">Telefon: {phone}</div>
    <div class="line">Adres: {address}</div>
    <div class="sec-title">Gönderici</div>
    <pre style="white-space:pre-wrap; margin:0;">{sender_block}</pre>
  </div>
  <a id="print-btn" href="#" onclick="window.print();return false;"
     style="display:block;text-align:center;margin:10px 8mm;padding:.6rem;border:1px solid #ddd;border-radius:8px;text-decoration:none;">
     🖨️ Yazdır
  </a>
</body>
</html>
"""
    return "data:text/html;base64," + base64.b64encode(html_block.encode("utf-8")).decode("ascii")

st.title("Kaffesa Kargo Etiket Oluşturucu By okanLab")
st.markdown(
    "- Solda alıcı satırlarını gir.\n"
    "- Sağda her alıcı için **kargo ücreti (ÜA/ÜG)** seç; ardından **tek sayfalık PDF indir** veya **tarayıcıdan yazdır**."
)

with st.sidebar:
    st.subheader("Alıcı Bilgileri (kopyala–yapıştır)")
    st.caption("Sütun sırası örnek: İsim/Firma | Telefon | Adres")
    raw = st.text_area(
        "Her satır bir alıcıyı temsil eder. Sütunları ; veya , veya TAB ile ayırabilirsin.",
        height=220,
        placeholder="Ör:\nAcme A.Ş.; 0532 000 00 00; Cumhuriyet Cad. No:12 Şişli İstanbul\nBurcu Girer, 0505 111 22 33, ...",
    )
    sep = st.radio("Ayraç", [",", ";", "TAB"], horizontal=True)
    sep_char = "\t" if sep == "TAB" else sep

rows = []
for line in raw.splitlines():
    parts = [p.strip() for p in line.split(sep_char) if p.strip()]
    if len(parts) >= 3:
        rows.append(
            {
                "name": parts[0],
                "phone": parts[1],
                "address": sep_char.join(parts[2:]) if len(parts) > 3 else parts[2],
            }
        )

if not rows:
    st.info("Sağda butonların gelmesi için soldaki kutuya en az 1 satır alıcı bilgisi gir.")
else:
    st.success(f"{len(rows)} alıcı bulundu. Her biri için ayrı **ÜA/ÜG seçimi** ve **tek sayfa PDF** butonu aşağıda.")
    for i, r in enumerate(rows, start=1):
        with st.container(border=True):
            st.markdown(f"**#{i} – {r['name']}**")
            st.write(f"**Telefon:** {r['phone']}")
            st.write(f"**Adres:** {r['address']}")

            pay_opt = st.radio(
                "Kargo ücreti",
                ["ÜA (Ücret Alıcı)", "ÜG (Ücret Gönderici)"],
                index=0,
                horizontal=True,
                key=f"pay_{i}"
            )
            pay_short = "ÜA" if "ÜA" in pay_opt else "ÜG"

            col1, col2 = st.columns([1,1])
            with col1:
                pdf_bytes = make_label_pdf(
                    r["name"], r["phone"], r["address"], SENDER_BLOCK, pay_short
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

            with col2:
                data_url = make_print_html(
                    r["name"], r["phone"], r["address"], SENDER_BLOCK, pay_short
                )
                st.markdown(
                    f'<a href="{data_url}" target="_blank" '
                    'style="display:block;text-align:center;padding:.6rem;border:1px solid #ddd;'
                    'border-radius:8px;text-decoration:none;">🖨️ Tarayıcıdan yazdır (tek sayfa)</a>',
                    unsafe_allow_html=True,
                )
