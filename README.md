# Quartz

Windows için Codex ve Antigravity CLI ajanlarını aynı çalışma alanında
birleştiren yerel masaüstü asistanı. Ana sohbet, proje seçimi, Squad
koordinasyonu ve görev kapsamlı Desktop Broker içerir.

Bu repo kaynak kod içindir; kullanıcı sohbetleri, hesap anahtarları, yerel
projeler, ekran görüntüleri, test kayıtları ve paketlenmiş EXE içermez.

## Durum ve sınırlar

- Normal sohbet, dosya/ekran/komut araçlarından ayrılır.
- Gerçek masaüstü görevleri uygulama kapsamı ve kullanıcı onayı gerektirir.
- Fare/klavye tek operatördedir; diğer ajan inceleme yapabilir.
- Warband profili Universal Modder üzerinden çalışır. Oyun, mod varlıkları,
  kayıtlar ve Universal Modder bu repoda dağıtılmaz.
- Windows Antigravity CLI inceleme modu tam işletim sistemi yalıtımı değildir.
  Onay, hedef pencere doğrulama ve Durdur korumalarını kaldırmayın.
- CLI/hesap/ağ gecikmeleri devam edebilir. Başarılı kaynak testi, gerçek
  masaüstü veya oyun kabulü anlamına gelmez.

## Geliştirme kurulumu

Güncel yerel doğrulama ortamı: Windows, Python 3.13 ve Node.js.
WebView2 Runtime gerekir. Kendi Codex / Antigravity CLI kurulumunuzu ve hesap
girişinizi kullanın; Quartz bu girişleri repoya taşımaz.
Grup görevleri için ayrıca Squad CLI gerekir (`QUARTZ_SQUAD_PATH` ile yol
belirtilebilir). Warband adaptörü için ayrı yerel Universal Modder kurulumu
ve açık proje kaydı gerekir.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python quartz_entry.py
```

`.env.example` yalnız boş anahtar alanları içerir. Gereken sağlayıcıyı yerelde
yapılandırın. Anahtar, parola veya CLI hesap verilerini commit etmeyin.
Varsayılan proje yolları bu bilgisayardaki eski kurulumdan gelir; başka
bilgisayarda kendi proje klasörünüzü Quartz üzerinden ekleyin.

## Test ve paketleme

```powershell
python -B scripts/run_safe_tests.py
python -B scripts/check_gui_javascript.py
python -B scripts/audit_publish.py --history
python build.py --require-brand
```

Güvenli test çalıştırıcı model sağlayıcılarını mock eder ve log/hafızayı geçici
alana yönlendirir; canlı model veya GUI kabulü değildir. Canlı kabul scriptleri
`scripts/` altındadır; çalıştırmadan önce ilgili kapsamı ve izinleri okuyun.

`build.py` ayrı staging dizininde paket üretir. `--deploy` yalnız kapalı Quartz
için test ve veri koruma doğrulamasıyla, eski dağıtımı yedekleyerek devreye
alır. Açık kullanıcı görevini veya sohbet dosyalarını silmeyin.

## Yapı

- `gui.py`: ana sohbet ve izin arayüzü.
- `core/agent_chat.py`, `core/message_intent.py`: sohbet/görev ayrımı ve tur yönetimi.
- `core/*_runtime.py`: gerçek CLI süreçleri.
- `core/desktop_*`, `core/natural_desktop.py`: görev kapsamlı bilgisayar kontrolü.
- `core/warband_workspace.py`: korumalı Universal Modder adaptörü.
- `tests/`: bağımsız kaynak regresyonları.
- `docs/`: mimari ve kapsamı belirtilmiş geçmiş kabul raporları.

## GitHub'a gönderme

Özel (`private`) repo hedeflenmiştir. Göndermeden önce staged içerik ve
gönderilecek geçmiş denetlenmelidir:

```powershell
python -B scripts/audit_publish.py --staged --history
git diff --cached --stat
```

Denetim bilinen anahtar biçimleri, yerel `.env` sırlarının birebir eşleşmesi ve
özel/runtime dosya adları için bir güvenlik ağıdır; bütün sırları bulacağının
garantisi değildir. Yalnız amaçlanan branch'i gönderin; `--mirror` / `--all`
ile yerel checkpoint ve test branch'lerini yayınlamayın.

Bir açık kaynak lisansı henüz seçilmemiştir; repo oluşturulması tek başına
yeniden dağıtım lisansı vermez. Üçüncü taraf CLI ve oyunların kendi koşulları
ayrı olarak geçerlidir.
