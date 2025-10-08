# index.py
# Final Versiyon (3. Revizyon): Gelen ham veriye özel, akıllı regex tabanlı parser.
# requirements: streamlit, reportlab

import io, os, re, base64, textwrap, unicodedata
import streamlit as st
import streamlit.components.v1 as components
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# -------------------------
# Ayarlar ve Sabitler
# -------------------------
st.set_page_config(page_title="Kargo Etiket Oluşturucu", layout="wide")

SENDER_BLOCK_DEFAULT = (
    "KAFFESA GIDA SANAYİ VE DIŞ TİCARET ANONİM ŞİRKETİ\n"
    "Adres: BALMUMCU MAH. BARBAROS BULVARI İBA BLOKLARI, 34/A\n"
    "İl/İlçe: Beşiktaş/İstanbul\n"
    "Tel: 0212 265 16 16\n"
)

# --- Font ve Logo Yükleme ---
FONT_PATH = "DejaVuSans.ttf"
if os.path.isfile(FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
        FONT_NAME = "DejaVuSans"
    except Exception: FONT_NAME = "Helvetica"
else: FONT_NAME = "Helvetica"

def load_logo_bytes():
    try:
        with open("logo.png", "rb") as f: return f.read()
    except FileNotFoundError: return None

# --- Yardımcı Fonksiyonlar ---
def normalize_pay_token(token: str) -> str | None:
    if not isinstance(token, str): return None
    t = unicodedata.normalize("NFKC", token).strip().lower().replace(" ", "")
    if t in ("üa", "ua"): return "ÜA"
    if t in ("üg", "ug"): return "ÜG"
    return None

def sanitize_filename(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", s)[:60] or "etiket"

def wrap_text_lines(text: str, max_chars: int):
    return textwrap.wrap(text or "", width=max_chars, replace_whitespace=False, drop_whitespace=True)

def get_pagesize(name="A4"):
    if name == "100x150": return (100*mm, 150*mm)
    if name == "A4": return A4
    return (148*mm, 210*mm)

def open_print_window_with_html(html: str):
    components.html(html, height=0, scrolling=False)

# --- Çizim ve HTML Fonksiyonları (Tam ve Çalışır Halde) ---
def draw_label_on_canvas(c: canvas.Canvas, W, H, recipient_name, phone, address, sender_block, pay_short, logo_bytes=None, badge_scale=1.7):
    margin_x, margin_y = 10*mm, 10*mm; usable_w = W - 2*margin_x
    scale = max(1.0, min(2.0, float(badge_scale))); c.setFillColorRGB(0.82, 0, 0)
    badge_w, badge_h = 30*mm*scale, 12*mm*scale
    c.roundRect(W - margin_x - badge_w, H - margin_y - badge_h, badge_w, badge_h, 3*mm*scale, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1); c.setFont(FONT_NAME, int(26*scale))
    c.drawCentredString(W - margin_x - badge_w/2, H - margin_y - badge_h/2 - (3*mm*scale), pay_short or "")
    c.setFillColorRGB(0, 0, 0)
    top_y = H - margin_y - 4*mm; used_h = 0
    if logo_bytes:
        try:
            img = ImageReader(io.BytesIO(logo_bytes))
            iw, ih = img.getSize(); target_w = 30 * mm; scale_f = target_w / iw; target_h = ih * scale_f
            c.drawImage(img, margin_x, top_y - target_h, width=target_w, height=target_h, mask='auto')
            used_h = target_h
        except Exception: used_h = 0
    c.setLineWidth(1.2); c.line(margin_x, H - margin_y - (used_h + 6*mm), margin_x + usable_w, H - margin_y - (used_h + 6*mm))
    y = H - margin_y - (used_h + 16*mm)
    c.setFont(FONT_NAME, 15); c.drawString(margin_x, y, "ALICI"); y -= 9*mm
    c.setFont(FONT_NAME, 28); c.drawString(margin_x, y, f"{recipient_name or ''}"); y -= 10*mm
    c.setFont(FONT_NAME, 18); approx_chars = int(usable_w / (3.7*mm))
    for line in wrap_text_lines(address or "", max(38, approx_chars)): y -= 8*mm; c.drawString(margin_x, y, line)
    y -= 8*mm; c.setFont(FONT_NAME, 16); c.drawString(margin_x, y, f"Tel: {phone or ''}")
    y -= 12*mm; c.setFont(FONT_NAME, 16); c.drawString(margin_x, y, "Gönderici"); y -= 8*mm
    c.setFont(FONT_NAME, 14)
    for line in (sender_block or "").split("\n"):
        if line.strip(): y -= 8*mm; c.drawString(margin_x, y, line)

def build_single_label_pdf(page_size_name, **kwargs):
    W, H = get_pagesize(page_size_name); buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H)); draw_label_on_canvas(c, W, H, **kwargs)
    c.showPage(); c.save(); buf.seek(0); return buf.getvalue()

def build_bulk_pdf(page_size_name, rows, sender_block, logo_bytes, badge_scale):
    W, H = get_pagesize(page_size_name); buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    for r in rows:
        draw_label_on_canvas(c, W, H, r.get("name"), r.get("phone"), r.get("address"), sender_block, r.get("final_pay", ""), logo_bytes=logo_bytes, badge_scale=badge_scale)
        c.showPage()
    c.save(); buf.seek(0); return buf.getvalue()

def make_print_html(recipient_name, phone, address, sender_block, pay_short, page_size_name="A4", logo_b64=None, badge_scale=1.7):
    # Bu fonksiyon tam ve çalışır halde.
    if page_size_name == "100x150": page_css = "@page { size: 100mm 150mm; margin: 8mm; }"
    elif page_size_name == "A4": page_css = "@page { size: A4; margin: 10mm; }"
    else: page_css = "@page { size: A5; margin: 8mm; }"
    pill_fs = int(22*badge_scale); pill_pad_v = int(6*badge_scale); pill_pad_h = int(14*badge_scale)
    logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height:auto; width:30mm; object-fit:contain; margin-right:8mm;" />' if logo_b64 else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Etiket</title><style>{page_css} body{{font-family:Arial,sans-serif;margin:0;padding:0;-webkit-print-color-adjust:exact;print-color-adjust:exact;}}.frame{{border:1px solid #000;padding:8mm;margin:8mm;position:relative;}}.pill{{position:absolute;top:8mm;right:8mm;font-weight:800;font-size:{pill_fs}px;color:#fff;background:#d00;padding:{pill_pad_v}px {pill_pad_h}px;border-radius:10px;}}.head{{display:flex;align-items:center;gap:8mm;margin-bottom:6mm;}}.sec{{font-weight:700;margin-top:6mm;font-size:15px;}}.r-name{{font-size:28px;font-weight:700;margin:4mm 0;}}.r-addr{{font-size:18px;line-height:1.35;white-space:pre-wrap;}}.r-phone{{font-size:16px;margin:2mm 0;}}.s-label{{font-size:16px;margin-top:10mm;font-weight:700;}}.s-body{{font-size:14px;white-space:pre-wrap;line-height:1.45;}}</style></head><body><div class="frame"><div class="pill">{pay_short}</div><div class="head">{logo_html}</div><div class="sec">ALICI</div><div class="r-name">{recipient_name}</div><div class="r-addr">{address}</div><div class="r-phone">Tel: {phone}</div><div class="s-label">Gönderici</div><div class="s-body">{sender_block}</div></div><script>window.onload=function(){{try{{window.focus();setTimeout(function(){{window.print();}},120);}}catch(e){{console.error(e);}}}};</script></body></html>"""

def make_bulk_print_html(page_size_name, rows, sender_block, logo_b64, badge_scale=1.7):
    pages=[]
    for r in rows: pages.append(f"""<div class="frame page"><div class="pill">{r.get('final_pay','')}</div><div class="head">{'<img src="data:image/png;base64,'+logo_b64+'" style="height:auto; width:30mm; object-fit:contain; margin-right:8mm;" />' if logo_b64 else ""}</div><div class="sec">ALICI</div><div class="r-name">{r.get('name','')}</div><div class="r-addr">{r.get('address','')}</div><div class="r-phone">Tel: {r.get('phone','')}</div><div class="s-label">Gönderici</div><div class="s-body">{sender_block}</div></div>""")
    if page_size_name == "100x150": page_css = "@page { size: 100mm 150mm; margin: 8mm; }"
    elif page_size_name == "A4": page_css = "@page { size: A4; margin: 10mm; }"
    else: page_css = "@page { size: A5; margin: 8mm; }"
    pill_fs = int(22*badge_scale); pill_pad_v = int(6*badge_scale); pill_pad_h = int(14*badge_scale)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Toplu Etiket Yazdır</title><style>{page_css} body{{font-family:Arial,sans-serif;margin:0;padding:0;-webkit-print-color-adjust:exact;print-color-adjust:exact;}}.frame{{border:1px solid #000;padding:8mm;margin:8mm;position:relative;}}.pill{{position:absolute;top:8mm;right:8mm;font-weight:800;font-size:{pill_fs}px;color:#fff;background:#d00;padding:{pill_pad_v}px {pill_pad_h}px;border-radius:10px;}}.head{{display:flex;align-items:center;gap:8mm;margin-bottom:6mm;}}.sec{{font-weight:700;margin-top:6mm;font-size:15px;}}.r-name{{font-size:28px;font-weight:700;margin:4mm 0;}}.r-addr{{font-size:18px;line-height:1.35;white-space:pre-wrap;}}.r-phone{{font-size:16px;margin:2mm 0;}}.s-label{{font-size:16px;margin-top:10mm;font-weight:700;}}.s-body{{font-size:14px;white-space:pre-wrap;line-height:1.45;}}.page{{page-break-after:always;}}</style></head><body>{''.join(pages)}<script>window.onload=function(){{try{{window.focus();setTimeout(function(){{window.print();}},120);}}catch(e){{console.error(e);}}}};</script></body></html>"""

# --- UI (Arayüz) ---
st.title("📦 Kargo Etiket Oluşturucu")

with st.sidebar:
    st.subheader("Excel'den Kopyalanan Veri")
    raw_input_data = st.text_area("Buraya yapıştırın:", height=350)

with st.expander("🔧 Tasarım & Gönderici Bilgileri", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        page_size_name = st.selectbox("Etiket Boyutu", ["A4", "A5", "100x150"], index=0)
    with col2:
        badge_scale = st.slider("Ücret Rozeti Boyutu", 1.0, 2.0, 1.7, 0.1)
    sender_block = st.text_area("Gönderici Bilgileri", value=SENDER_BLOCK_DEFAULT, height=140)

# =========================================================================================
# YENİ ve EN SAĞLAM VERİ OKUMA (PARSING) MANTIĞI
# =========================================================================================
rows = []
if raw_input_data:
    # Metni, her bir tarihin kendisiyle başlayacak şekilde bölüyoruz. Bu, 30'a 31 hatasını çözer.
    shipments = re.split(r'(?=\d{2}\.\d{2}\.\d{4})', raw_input_data)
    shipments = [s.strip() for s in shipments if s.strip()]

    for block in shipments:
        temp_block = block
        name, address, phone, payment = "", "", "", ""

        # 1. Telefonu bul ve metinden çıkar.
        phone_match = re.search(r'(\+?\d[\d\s\-\(\)]{8,}\d)', temp_block)
        if phone_match:
            phone = phone_match.group(1).strip()
            temp_block = temp_block.replace(phone, ' ')

        # 2. Kargo Ödemesini (ÜA/ÜG) bul ve metinden çıkar.
        payment_match = re.search(r'\b(ÜA|UA|ÜG|UG)\b', temp_block, re.IGNORECASE)
        if payment_match:
            payment = payment_match.group(1).upper().replace('U', 'Ü')
            # Metinden silerken orijinal halini kullanalım
            temp_block = temp_block.replace(payment_match.group(0), ' ')

        # 3. Adresi bul (içinde Mah, Sok, Cad, No geçen en uzun metin parçası) ve metinden çıkar
        address_match = re.search(r'([A-Za-z0-9\s\.,:/\\-]+(?:Mah|Sok|Cad|No)[\w\s\./:;-]+)', temp_block, re.IGNORECASE)
        if address_match:
            address = address_match.group(1).strip()
            temp_block = temp_block.replace(address, ' ')

        # 4. İsmi bul (FATURA/İRSALİYE'den önceki en mantıklı metin)
        # Bu, verinizdeki en tutarlı desendi.
        name_anchor_match = re.search(r'(.+?)(FATURA|İRSALİYE|irsaliye)', temp_block, re.DOTALL)
        if name_anchor_match:
            # Anchor'dan önceki kısımda, genellikle sonda yer alan ismi alıyoruz.
            before_anchor = name_anchor_match.group(1)
            potential_names = re.findall(r'([A-ZĞÜŞİÖÇ][a-zA-ZĞÜŞİÖÇ\s\."]+)', before_anchor)
            if potential_names:
                # Genellikle son bulunan isim doğru oluyor.
                name = potential_names[-1].strip()
                temp_block = temp_block.replace(name, ' ')

        # 5. Eğer hala adres bulunamadıysa (Showroom teslimatları gibi), kalan metni adres/not olarak ata
        if not address:
            # Baştaki tarihi ve bilinen anahtar kelimeleri temizle
            remaining_text = re.sub(r'^\d{2}\.\d{2}\.\d{4}\s*', '', temp_block)
            remaining_text = re.sub(r'(SHOWROOM|TESLİMAT|FATURA|İRSALİYE|irsaliye|KARGO|UP)', '', remaining_text, flags=re.IGNORECASE)
            address = re.sub(r'\s{2,}', ' ', remaining_text).strip() # Fazla boşlukları temizle

        # Sadece ismi bulunabilen kayıtları ekle
        if name:
            rows.append({
                "name": name,
                "address": address,
                "phone": phone,
                "parsed_pay": normalize_pay_token(payment),
            })
# =========================================================================================

# --- Sonuçların Gösterilmesi ---
if not rows:
    st.info("İşlem yapmak için soldaki alana Excel'den veri yapıştırın.")
else:
    st.success(f"{len(rows)} adet geçerli alıcı bilgisi bulundu.")
    logo_bytes = load_logo_bytes()
    logo_b64 = base64.b64encode(logo_bytes).decode("ascii") if logo_bytes else None

    for i, r in enumerate(rows, start=1):
        with st.container():
            st.markdown(f"---")
            st.markdown(f"**#{i} – {r.get('name')}**")
            st.markdown(f"**Adres/Notlar:** {r.get('address', 'N/A')}")
            st.markdown(f"**Telefon:** {r.get('phone', 'N/A')}")
            default_index = 1 if r.get("parsed_pay") == "ÜG" else 0
            pay_opt = st.radio("Kargo Ödemesi", ["ÜA (Ücret Alıcı)", "ÜG (Ücret Gönderici)"], index=default_index, horizontal=True, key=f"pay_{i}")
            rows[i-1]["final_pay"] = "ÜA" if "ÜA" in pay_opt else "ÜG"
            col1, col2 = st.columns(2)
            with col1:
                pdf_bytes = build_single_label_pdf(page_size_name, recipient_name=r.get("name"), phone=r.get("phone"), address=r.get("address"), sender_block=sender_block, pay_short=rows[i-1]["final_pay"], logo_bytes=logo_bytes, badge_scale=badge_scale)
                st.download_button(label="📄 PDF İndir", data=pdf_bytes, file_name=f"etiket_{sanitize_filename(r.get('name'))}.pdf", mime="application/pdf", use_container_width=True, key=f"dl_{i}")
            with col2:
                if st.button("🖨️ Yazdır", key=f"print_{i}", use_container_width=True):
                    html_content = make_print_html(r.get("name"), r.get("phone"), r.get("address"), sender_block, rows[i-1]["final_pay"], page_size_name=page_size_name, logo_b64=logo_b64, badge_scale=badge_scale)
                    open_print_window_with_html(html_content)

    if len(rows) > 1:
        st.markdown("---")
        st.subheader("Toplu İşlemler")
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            bulk_pdf_bytes = build_bulk_pdf(page_size_name, rows, sender_block, logo_bytes, badge_scale)
            st.download_button(label="📦 Toplu PDF İndir", data=bulk_pdf_bytes, file_name="etiketler_toplu.pdf", mime="application/pdf", use_container_width=True)
        with t_col2:
            if st.button("🖨️ Toplu Yazdır", use_container_width=True):
                bulk_html_content = make_bulk_print_html(page_size_name, rows, sender_block, logo_b64, badge_scale)
                open_print_window_with_html(bulk_html_content)
