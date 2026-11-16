# Kaffesa Personel — `kaffesa.com/app/`

Personel için şifreli araç sayfası. İlk araç: **Kargo Etiket Programı**. Render'daki Streamlit programının (`index.py`) tarayıcıda çalışan karşılığıdır.

- Sunucuda kod çalışmaz. Sunucu sadece tek bir HTML dosyası gönderir, etiketler personelin tarayıcısında oluşturulur.
- Müşteri ad/adres/telefon bilgileri hiçbir sunucuya gönderilmez.
- Sayfanın içeriği AES-256-GCM ile şifrelidir. Şifre bilinmeden program açılmaz ve kodu okunamaz.
- Arama motorlarına kapalıdır (`noindex`).

## Dosyalar

```text
web/
├── build.mjs              # Şifreli app/index.html'i üretir (Node 18+, ek paket yok)
├── src/
│   ├── app.html           # Araç menüsü + kargo programı arayüzü
│   ├── kargo-core.js      # Excel okuma, etiket PDF'i, yazdırma (index.py ile aynı ölçüler)
│   └── lock.html          # Şifre ekranı
├── assets/                # logo.png (etiket), logo-ui.png (arayüz), DejaVuSans-tr.ttf (Türkçe alt küme)
└── vendor/jspdf.umd.min.js  # PDF kütüphanesi (jsPDF 2.5.2)
```

## Derleme / şifre değiştirme

```bash
cd web
node build.mjs            # şifreyi sorar (en az 8 karakter)
```

Çıktı: `web/dist/app/index.html`. Şifre her değiştiğinde bu komut yeniden çalıştırılır ve yeni dosya siteye yüklenir. Eski şifre o anda geçersiz olur.

## kaffesa.com'a ekleme

1. `dist/app/index.html` dosyasını kaffesa.com deposunun kökünde `app/index.html` olarak koyun.
2. Footer'a personel linkini ekleyin: `<a href="/app/">Personel</a>`
3. Commit + push. Pipeline siteyi yayınlar.

## Python sürümünden farklar

- Etiket PDF'i ve yazdırma tasarımı aynıdır (ReportLab çıktısıyla piksel karşılaştırması yapıldı).
- Excel okuma aynıdır. Tek fark: sadece rakamdan oluşan telefonlarda (`05551112233`) baştaki **0 artık silinmez**.
- Etiket boyutu, rozet boyutu ve şube seçimi o tarayıcıda hatırlanır.
- Yazdırma, gizli bir çerçeve üzerinden tarayıcının yazdır penceresini açar. Açılmazsa "PDF İndir" kullanılabilir.
