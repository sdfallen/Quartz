# Quartz arayüzü: sıfırdan yeniden tasarım (4 Kasım 2026)

Dal: `claude/ui-redesign-20261104`, taban `19601a2` (`claude/focus-persist-20261104`).
Kullanıcı eski arayüzü, renkleri ve logoyu örnek alınmadan baştan istedi.

## Kararlar

- **Yerleşim:** Kenar çubuğu, ortalanmış sohbet ve gerektiğinde açılan Durum/Araçlar/Günlük paneli.
  Ajan ve model seçimi mesaj kutusuna taşındı; yalnız seçili ajanın modeli görünür.
- **Renk:** Sıcak grafit zemin, tek vurgu. Varsayılan vurgu pembe kuvars; sitrin, ametist ve dumanlı
  kuvars seçilebilir. Koyu, açık ve sistem teması var. Durdur düğmesi vurgudan bağımsız düz kırmızıdır.
- **Logo:** Altı yüzlü kuvars kristali olan bir Q. Tek geometri `scripts/build_brand_assets.py` içinde;
  SVG, PNG ve 16–256 px ICO ondan üretilir. 32 px altında yüzeyler tek tona iner.
- **Yazı:** Çevrimdışı çalışmak için sistem yazıları (Segoe UI Variable, Segoe UI, Cascadia/Consolas).
- **Hareket:** Yalnız neden-sonuç anlatan hareket: mesaj gelişi, panel ve pencere açılışı, sürgülü seçici,
  ajan çalışırken logoda dolaşan ışık, kısa açılış. Boşta ekran durur. `prefers-reduced-motion` ve
  düşük donanım modunda hepsi kapanır.

## Yenilikler

- Komut paleti (`Ctrl+K`): komutlar ve sohbet arama. Var olan düğmelere basar; silme, gönderme ve onay
  komutu içermez. Görev sürerken en üstte durdurma komutu çıkar.
- Kısayollar: `Ctrl+B` kenar çubuğu, `Ctrl+I` panel, `Esc` katman kapatma. `Ctrl+L` korundu.
- Çok satırlı, içerikle büyüyen mesaj kutusu (`Shift+Enter` yeni satır).
- Boş sohbette başlangıç önerileri. Öneri yalnız metni doldurur, kendiliğinden göndermez.
- Kod bloğunda kopyala düğmesi.
- Tema ve vurgu `%LOCALAPPDATA%\Quartz\ui-preferences.json` içinde saklanır ve ilk boyamadan önce uygulanır.
- Pencere ilk açılışta ve kompakt moddan dönüşte çalışma alanına sığdırılır. Eski ayarla 1366×768
  ekranda pencere (104,104) konumunda açılıyor, mesaj kutusunun altı ekran dışında kalıyordu.

## Korunanlar

- Pywebview API adları ve payload'ları; yalnız `ui_preferences` ve `ui_set_preference` eklendi.
- Stop denetimleri: hareketsiz, her zaman tıklanabilir. Masaüstü oturumunda şeritteki Stop gizlenir,
  aynı işi yapan üst çubuk görünür kalır.
- Yanıt, izin, yazıcı ve görev mantığı. JavaScript değişiklikleri görünüm ile sınırlıdır.
- Kullanıcı imzası ve Türkçe arayüz.

## Sahiplik ve integration request

`gui.py`, `ui/`, `core/ui_*.py` ve `tests/test_gui_*.py` Claude sahipliğindedir. Kullanıcının açık logo
isteği için aşağıdakiler de değişti; Codex'in incelemesi gerekir:

- `assets/branding/*`, `assets/workspace.css`: dosya adları aynı, `Quartz.spec` değişmedi.
- `scripts/build_brand_assets.py` (yeni). `scripts/import_brand_icon.py` ve kökteki eski görseller duruyor.
- `tests/test_branding.py`: "kullanıcının verdiği dosyayla birebir aynı" testi, üreteçle eşleşme testine dönüştü.
- `tests/test_self_diagnostics_ui.py`: logo erişilebilirlik adı.
- `.gitattributes` (yeni): `quartz-q.svg` satır sonu dönüşümünden muaf. Özeti manifestte kayıtlı; `core.autocrlf`
  açıkken yeni checkout'ta CRLF'ye dönüşüp `test_committed_assets_match_the_generator` testini bozuyordu.
- `core/branding.py` ve `assets/branding/README.md` içindeki "logo üretilmez" ifadesi eskidi (README güncellendi).

## Kanıt seviyeleri

Kesin sonuçlar ve sayılar teslim mesajında ve PR'da yazılır. Gerçek arka uçla, gerçek görevle yapılan
GUI kabulü ayrıdır; o yapılana kadar LIVE VERIFIED denmez.
