# Quartz

Windows için Codex ve Antigravity CLI ajanlarını aynı çalışma alanında
birleştiren yerel masaüstü asistanı. Ana sohbet, proje seçimi, Squad
koordinasyonu ve görev kapsamlı Desktop Broker içerir.

Bu repo kaynak kod içindir; kullanıcı sohbetleri, hesap anahtarları, yerel
projeler, ekran görüntüleri, test kayıtları ve paketlenmiş Quartz EXE içermez.
Küçük MIT lisanslı Squad yardımcısı, lisansı ve hash/provenance kaydıyla
`assets/bin/` altında bulunur.

**30 Ekim 2026:** REA destekli öz teşhis, sohbet içi teşhis kartı, bağımsız
CLI/onboarding ve temiz dağıtım hazırlığı bu kaynak ağacına dahildir.
[Yan bilgisayarda geliştirmeye devam etme rehberi](docs/SECOND_COMPUTER_DEVELOPMENT.md).

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

Güncel yerel doğrulama ortamı: Windows x64, Python 3.13 ve Node.js.
Geliştirici JS testleri için Node PATH üzerinde olmalıdır. REA 6.8.0 için
Node 22.23.4+, 24.22.1+ veya 26.12.1+ desteklenir; özel kurulum yardımcısı
uygun taşınabilir Node'u hazırlayabilir.
Codex Desktop veya Antigravity Desktop/IDE gerekmez. İlk açılış sihirbazı
eksik Codex/agy CLI araçlarını hazırlar; resmî hesap girişini kullanıcı tamamlar.
WebView2 eksikse GUI başlamadan resmî kurulum adımı sunulur.
Hesap bağlantıları repoya taşınmaz. Squad yardımcısı pakette/repoda bulunur;
isteğe bağlı farklı yol için `QUARTZ_SQUAD_PATH` kullanılabilir.
Warband adaptörü için ayrı yerel Universal Modder kurulumu
ve açık proje kaydı gerekir.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe quartz_entry.py
```

`.env` hesapla ilk kurulum için zorunlu değildir. API anahtarı tercih ediliyorsa
`.env.example` dosyası yerelde kopyalanabilir; yalnız boş alanlar içerir.
Anahtar, parola veya CLI hesap verilerini commit etmeyin.
Varsayılan proje yolları bu bilgisayardaki eski kurulumdan gelir; başka
bilgisayarda kendi proje klasörünüzü Quartz üzerinden ekleyin.

## Test ve paketleme

```powershell
python -B scripts/run_safe_tests.py
python -B scripts/check_gui_javascript.py
python -B scripts/audit_publish.py --history
python build.py --require-brand
```

Güvenli test çalıştırıcı yerel `.env` dosyasını yüklemez; SDK kurulumu için
yalnız sahte test anahtarı kullanır. Model sağlayıcıları testlerde mock edilir,
log/hafıza geçici alana yönlendirilir; canlı model veya GUI kabulü değildir. Canlı kabul scriptleri
`scripts/` altındadır; çalıştırmadan önce ilgili kapsamı ve izinleri okuyun.
Gerçek yerel Squad roundtrip testleri Squad CLI veya derlenmiş guard yardımcısı
yoksa açıkça SKIPPED raporlanır. Bunları da çalıştırmak için paketli Squad
yardımcısını kullanın ve guard yardımcısını üretin (derlenen guard EXE repoya gönderilmez):

```powershell
python -m PyInstaller --noconfirm --onefile --console --name QuartzDesktopMCP --distpath build/desktop-helper --workpath build/helper-work --specpath build/helper-spec core/desktop_mcp.py
```

`build.py` ayrı staging dizininde paket üretir. `--deploy` yalnız kapalı Quartz
için test ve veri koruma doğrulamasıyla, eski dağıtımı yedekleyerek devreye
alır. Açık kullanıcı görevini veya sohbet dosyalarını silmeyin.

## REA destekli öz teşhis

REA isteğe bağlıdır; normal sohbet veya diğer ajan bağlantıları için gerekmez.
Yerel hazırlık:

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_rea_tool.py
```

Bu işlem sabit `rea-agents@6.8.0` sürümünü kullanıcıya özel klasöre kurar;
global npm/PATH veya ajan kayıtlarını değiştirmez. Normal teşhis başlatılması
kendiliğinden indirme yapmaz.

Sohbet komutları: `Öz teşhis başlat`, `REA olmadan öz teşhis başlat`,
`Öz teşhisi durdur`. Kaynak modunda paket yoksa paket kontrolleri NOT_TESTED
olması beklenir. Tam statik paket kontrolü için manifest içeren derlenmiş
dağıtım kullanılmalıdır. Otomatik onarım yoktur.

[Teknik kapsam ve gerçek kabul sınırları](docs/QUARTZ_SELF_DIAGNOSTICS_20261030.md)
ile [backend/arayüz sözleşmesi](docs/SELF_DIAGNOSTICS_CONTRACT.md) birlikte okunmalıdır.
Son yerel tam regresyon 607 test geçti; paketlenmiş ana sohbetten teşhis gönderimi
masaüstü girdi erişimi nedeniyle henüz canlı doğrulanmadı. Eski kanıtlar yeni
makinenin veya yeni build'in kabulü sayılmaz.

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
