# index.py
# requirements: streamlit, reportlab, pandas
# Düzeltme: 2025-10-08 — Gemini tarafından tek satır yapıştırma mantığına göre yeniden yapılandırıldı.

import io, os, re, base64, textwrap, unicodedata
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

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
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
        FONT_NAME = "DejaVuSans"
    except Exception:
        FONT_NAME = "Helvetica"
        st.warning("DejaVuSans.ttf yüklenemedi, Helvetica kullanılacak.")
else:
    FONT_NAME = "Helvetica"
    st.warning("DejaVuSans.ttf bulunamadı. PDF’te Türkçe karakterlerde sorun olabilir.")

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
    # Metin içinden de bulabilmek için boşluklu hallerini de ekledik
    t = unicodedata.normalize("NFKC", token).strip().lower().replace(" ", "")
    if t in ("üa", "ua", "ücretalıcı"): return "ÜA"
    if t in ("üg", "ug", "ücretgönderici"): return "ÜG"
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
    c.line(margin, H-margin, margin+len_, H-margin)
    c.line(margin, H-margin, margin, H-margin-len_)
    c.line(W-margin-len_, H-margin, W-margin, H-margin)
    c.line(W-margin, H-margin, W-margin, H-margin-len_)
    c.line(margin, margin, margin+len_, margin)
    c.line(margin, margin, margin, margin+len_)
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

def get_pagesize(name="A4"):
    if name == "100x150": return (100*mm, 150*mm)
    if name == "A4": return A4
    return (148*mm, 210*mm)

def open_print_window_with_html(html: str):
    components.html(html, height=0, scrolling=False)

def draw_label_on_canvas(
    c: canvas.Canvas, W, H,
    recipient_name, phone, address, sender_block, pay_short,
    logo_bytes=None, badge_scale=1.7
):
    margin_x, margin_y = 10*mm, 10*mm
    usable_w = W - 2*margin_x
    draw_cut_marks(c, W, H)

    scale = max(1.0, min(2.0, float(badge_scale)))
    c.setFillColorRGB(0.82, 0, 0)
    badge_w, badge_h = 30*mm*scale, 12*mm*scale
    c.roundRect(W - margin_x - badge_w, H - margin_y - badge_h, badge_w, badge_h, 3*mm*scale, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(FONT_NAME, int(26*scale))
    c.drawCentredString(W - margin_x - badge_w/2, H - margin_y - badge_h/2 - (3*scale), pay_short or "")
    c.setFillColorRGB(0, 0, 0)

    top_y = H - margin_y - 4*mm
    used_h = 0
    if logo_bytes:
        used_h = place_logo(c, logo_bytes, margin_x, top_y, width_mm=30)

    c.setLineWidth(1.2)
    c.line(margin_x, H - margin_y - (used_h + 6*mm), margin_x + usable_w, H - margin_y - (used_h + 6*mm))

    y = H - margin_y - (used_h + 16*mm)
    c.setFont(FONT_NAME, 15)
    c.drawString(margin_x, y, "ALICI")
    y -= 9*mm
    c.setFont(FONT_NAME, 28)
    c.drawString(margin_x, y, f"{recipient_name or ''}")
    y -= 10*mm
    c.setFont(FONT_NAME, 18)
    approx_chars = int(usable_w / (3.7*mm))
    for line in wrap_text_lines(address or "", max(38, approx_chars)):
        y -= 8*mm
        c.drawString(margin_x, y, line)

    y -= 8*mm
    c.setFont(FONT_NAME, 16)
    c.drawString(margin_x, y, f"Tel: {phone or ''}")

    y -= 12*mm
    c.setFont(FONT_NAME, 16)
    c.drawString(margin_x, y, "Gönderici")
    y -= 8*mm
    c.setFont(FONT_NAME, 14)
    for line in (sender_block or "").split("\n"):
        if line.strip():
            y -= 8*mm
            c.drawString(margin_x, y, line)
    c.rect(margin_x-4*mm, margin_y, usable_w+8*mm, H - 2*margin_y)

def build_single_label_pdf(page_size_name, **kwargs):
    W, H = get_pagesize(page_size_name)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    draw_label_on_canvas(c, W, H, **kwargs)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

def build_bulk_pdf(page_size_name, rows, sender_block, logo_bytes, badge_scale):
    W, H = get_pagesize(page_size_name)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    for r in rows:
        pay_short = r.get("final_pay", "")
        draw_label_on_canvas(
            c, W, H,
            r.get("name"), r.get("phone"), r.get("address"),
            sender_block, pay_short,
            logo_bytes=logo_bytes, badge_scale=badge_scale
        )
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

# (HTML oluşturma fonksiyonları `make_print_html` ve `make_bulk_print_html` değişmediği için burada yer kaplamaması adına çıkarıldı.
# Kendi kodunuzdaki hallerini koruyabilirsiniz veya isterseniz tam halini tekrar ekleyebilirim.)
def make_print_html(*args, **kwargs): return "<div>Yazdırma Devre Dışı</div>" # Placeholder
def make_bulk_print_html(*args, **kwargs): return "<div>Yazdırma Devre Dışı</div>" # Placeholder
# YUKARIDAKI 2 FONKSİYONU KENDİ KODUNUZDAKİ ORİJİNALLERİYLE DEĞİŞTİRİN.

# -------------------------
# UI
# -------------------------
st.title("Kargo Etiket Oluşturucu")

with st.sidebar:
    st.subheader("Alıcı Bilgileri (Excel’den kopyala–yapıştır)")
    raw = st.text_area(
        "Excel’den tek veya çok sayıda satırı kopyalayıp buraya yapıştırın.",
        height=300,
        placeholder="07.10.2025SHOWROM TESLİMAT... GÖKBERK ÇIRAKOĞLU...\n08.10.2025 E-TİCARET... ABC FİRMA...",
    )

st.markdown(
    "- **Yöntem:** Yapıştırılan metin içinden İsim, Telefon ve Adres bilgileri akıllıca ayrıştırılır.\n"
    "- **Çoklu Giriş:** Her satırın başındaki `dd.mm.yyyy` formatındaki tarih, yeni bir gönderi olarak kabul edilir."
)

with st.expander("🔧 Tasarım & Seçenekler"):
    colA, colB = st.columns(2)
    with colA:
        page_size_name = st.selectbox("Etiket Boyutu", ["A5", "A4", "100x150"], index=1)
        sender_block = st.text_area("Gönderici Bloğu", value=SENDER_BLOCK_DEFAULT, height=140)
    with colB:
        badge_scale = st.slider("Ücret rozeti ölçeği (1×–2×)", 1.0, 2.0, 1.7, 0.1)

# =========================================================================================
# YENİ VE DÜZELTİLMİŞ VERİ OKUMA (PARSING) MANTIĞI
# =========================================================================================
rows = []
if raw:
    # Farklı sistemlerden gelen satır sonlarını standartlaştır
    raw_norm = raw.replace("\r\n", "\n").replace("\r", "\n")

    # 1. Adım: Tüm metni, satır başında tarih gördüğü yerlerden bölerek gönderilere ayır.
    # Bu sayede birden fazla satır yapıştırılsa bile her biri ayrı işlenir.
    shipments = re.split(r'(?m)(?=^\s*\d{2}\.\d{2}\.\d{4})', raw_norm)
    shipments = [s.strip() for s in shipments if s.strip()]

    # 2. Adım: Her bir gönderi metnini tek tek işle
    for block in shipments:
        remaining_block = block
        
        # 2a. Telefonu Bul: Metnin herhangi bir yerindeki telefon numarasını regex ile bul.
        phone_match = re.search(r'(\+?\d[\d\s\-\(\)]{8,}\d)', remaining_block)
        phone_cell = phone_match.group(1).strip() if phone_match else ""
        if phone_cell:
            remaining_block = remaining_block.replace(phone_cell, " ").strip()

        # 2b. İsmi Bul: Metin içindeki en az iki kelimeden oluşan BÜYÜK HARFLİ ilk ifadeyi isim olarak kabul et.
        # Örnek: "GÖKBERK ÇIRAKOĞLU" veya "ABC FİRMA LTD" gibi yapıları yakalar.
        name_match = re.search(r'\b([A-ZĞÜŞİÖÇ]{2,}\s+[A-ZĞÜŞİÖÇ\s]+)\b', remaining_block)
        name_cell = name_match.group(1).strip() if name_match else ""
        if name_cell:
             remaining_block = remaining_block.replace(name_cell, " ").strip()

        # 2c. Kargo Ödemesini Bul: Metinde "ÜA" veya "ÜG" ara.
        pay_match = re.search(r'\b(ÜA|UA|ÜG|UG)\b', block, re.IGNORECASE)
        pay_cell = pay_match.group(1) if pay_match else ""
        parsed_pay = normalize_pay_token(pay_cell)

        # 2d. Adresi Belirle: Geriye kalan her şey adrestir.
        # Başındaki tarihi ve gereksiz boşlukları temizle.
        addr_cell = re.sub(r'^\s*\d{2}\.\d{2}\.\d{4}\s*', '', remaining_block).strip()
        addr_cell = re.sub(r'\s{2,}', ' ', addr_cell) # Çoklu boşlukları teke indir

        # Sadece içinde anlamlı bir veri olan kayıtları listeye ekle
        if any([name_cell, phone_cell, addr_cell]):
            rows.append({
                "name": name_cell,
                "phone": phone_cell,
                "address": addr_cell,
                "parsed_pay": parsed_pay,
            })
# =========================================================================================

# UI: Son kontroller ve butonlar (Bu kısım aynı kalabilir)
if not rows:
    st.info("Sağda butonların gelmesi için soldaki kutuya Excel’den en az 1 satır yapıştır.")
else:
    st.success(f"{len(rows)} alıcı bulundu. Kargo ödemesi (ÜA/ÜG) için son kontrol yapıp yazdır/indir.")
    logo_bytes = load_logo_bytes()
    logo_b64 = base64.b64encode(logo_bytes).decode("ascii") if logo_bytes else None

    for i, r in enumerate(rows, start=1):
        st.markdown(f"**#{i} – {r.get('name','(İSİM BULUNAMADI)')}**")
        if r.get("address"): st.write(f"**Adres:** {r.get('address')}")
        if r.get("phone"):   st.write(f"**Telefon:** {r.get('phone')}")

        default_index = 0
        if r.get("parsed_pay") == "ÜG": default_index = 1
        
        pay_opt = st.radio("Kargo ödemesi", ["ÜA (Ücret Alıcı)", "ÜG (Ücret Gönderici)"],
                           index=default_index, horizontal=True, key=f"pay_{i}")
        pay_short = "ÜA" if "ÜA" in pay_opt else "ÜG"
        rows[i-1]["final_pay"] = pay_short

        col1, col2 = st.columns([1,1])
        with col1:
            try:
                pdf_bytes = build_single_label_pdf(
                    page_size_name, recipient_name=r.get("name"), phone=r.get("phone"), address=r.get("address"),
                    sender_block=sender_block, pay_short=pay_short,
                    logo_bytes=logo_bytes, badge_scale=badge_scale
                )
                file_name = f"etiket_{sanitize_filename(r.get('name') or 'alici')}.pdf"
                st.download_button(label="📄 PDF indir", data=pdf_bytes, file_name=file_name,
                                   mime="application/pdf", use_container_width=True, key=f"dl_{i}")
            except Exception as e:
                st.error(f"PDF oluşturulamadı: {e}")
        with col2:
            if st.button("🖨️ Yazdır", key=f"print_{i}", use_container_width=True):
                # ÖNEMLİ: HTML fonksiyonlarını kendi kodunuzdan geri eklemeyi unutmayın
                st.warning("Yazdırma fonksiyonu tijdelijk devre dışı.")
    
    # Toplu İşlemler
    st.markdown("### Toplu işlemler")
    # ... (Bu kısım da aynı kalabilir)
