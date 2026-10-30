# Quartz — yeni bilgisayara dağıtım ve ilk bağlantı

29 Ekim 2026. Kapsam: kurulum, CLI hazırlığı, kişisel veriden arındırılmış dağıtım.
ASTER/Warband ve düşük donanım algoritmaları bu çalışmada değiştirilmedi.

## Uygulanan akış

- `core/cli_installer.py`: bağımsız agy kurulumu. Google'ın resmî Windows kurucusunun kullandığı manifest; platform seçimi; SHA-512; geçerli **Google LLC** Authenticode imzası; gerçek `--version` kontrolü. Bu kontrollerden sonra özel sürüm klasörü ve atomik kurulum manifesti yayımlanır. Eski ikili üzerine yazılmaz. Resmî PowerShell betiği indirilip çalıştırılmaz; doğrulanmış ikili doğrudan kullanılır.
- Konum `%LOCALAPPDATA%\Quartz\bin\packages\agy-<sürüm>-<id>\agy.exe`. Kullanıcının mevcut agy/PATH kurulumu varsa önce kullanılabilirliği denetlenir. Registry veya kalıcı PATH değiştirilmez. Desktop, IDE veya önceden Node kurulumu gerekmez. agy'nin kendi sonraki güncelleme davranışı sağlayıcısına aittir.
- `core/install_security.py`: izinli HTTPS host/path, her yönlendirmeden önce kontrol, akışlı ve boyut/zaman sınırlı indirme, yerel Authenticode kontrolü. Hash/imza hatasında ikili çalıştırılmaz.
- `core/onboarding.py`: **Hesabımla bağlan → Google** agy eksikse kurar, sonra resmî etkileşimli CLI'yı açar. Kurulum düğmesi de bu yolu kullanır. Google API anahtarı ayrı Gemini CLI yoludur. Açık giriş varken ikinci giriş süreci başlatılmaz. Hazır mevcut bağlantı yeniden girişe zorlanmaz; tek sağlayıcı yeterlidir.
- Codex: mevcut resmî CLI kurulumu ve `codex login` korunur. Anahtar kullanımı ayrı bir seçenektir; ChatGPT hesabından ücretli API'ye sessiz geçiş yapılmaz. Bağlantı doğrulaması ile model/kota erişimi ayrı kavramlardır.
- `core/windows_prerequisites.py` ve `quartz_entry.py`: backend/GUI başlamadan HKCU/HKLM 32/64-bit WebView2 `pv` denetimi. Eksikse WebView2 gerektirmeyen Türkçe yerel pencere, kullanıcının onayıyla resmî Evergreen bootstrapper indirme, **Microsoft Corporation** imzası, `/silent /install`, ardından tekrar runtime denetimi. Başarısız/iptal edilen kurulumda backend açılmaz; resmî sayfaya yönlendirme vardır. Quartz yönetici yükseltmesi istemez; Microsoft'un per-user/per-machine kuralları geçerlidir.

## Dağıtım sınırı

Çalışan `dist/Quartz` kullanıcı verileriyle birlikte korunur; yeni kullanıcıya kopyalanmaz.

`Quartz.spec` yalnız gerekli Q görselleri, CSS, lisans/provenance ve Squad ikilisini açık listeyle alır. Yerel kaynak yolları içeren geliştirme logo manifesti pakete alınmaz.

`scripts/prepare_distribution.py` yalnız yeni ve temiz PyInstaller staging paketinden ayrı hedef oluşturur. Kirli kaynak klasörü veya mevcut hedef reddedilir. `.env`, sohbet/hafıza/proje dosyaları, silinen sohbet arşivleri, CLI oturumları, çerezler, WebView profilleri ve log/veritabanı dosyaları denetimde reddedilir. Bilinen yerel `.env` sırları da içerikte aranır; değerler rapora yazılmaz. SHA-256 dosya manifesti sonraki değişiklikleri saptar. Bu denetim genel amaçlı tüm sırları bulma garantisi değildir; asıl koruma temiz staging ve açık kaynak listesidir.

`build_installer.ps1 -PackageDir <temiz-paket>` zorunlu paket gizlilik denetimini ve kaynak/EXE eşleşmesini geçirmeden setup derlemez. Eski setup üzerine yazılmaz. Yeni varsayılan kurulum kullanıcıya yazılabilir `%LOCALAPPDATA%\Programs\Quartz`; otomatik Windows başlangıcı seçeneği kapalıdır. Mevcut yerel dağıtım güncellenmedi.

## Gerçek kabul sınırları

Kurulum unit testleri gerçek hesap girişinin yerine geçmez. İzole klasörde gerçek indirme/ikili çalıştırma da temiz Windows VM değildir. Bu makinenin Google/ChatGPT kimlik bilgileri pakete aktarılmadı, silinmedi veya yeniden giriş için kullanılmadı.

Temiz makinede yeni kullanıcının tarayıcı/CLI hesabına girişi, sağlayıcı kotası ve ardından model yanıtı ayrıca doğrulanmalıdır. Quartz parola veya doğrulama kodu toplamaz; kullanıcı resmî giriş adımını tamamlar.

## Yeni bilgisayarda kabul adımları

1. Güncel setup dosyasını kopyalayın; dosya SHA-256 değerini yanındaki `SHA256.txt` ile karşılaştırın. Kaynak klasöründeki eski Eylül setup'ını kullanmayın.
2. Quartz'ı kurup açın. WebView2 yoksa resmî runtime kurulumunu onaylayın. Var olan runtime'ın yeniden kurulmaması beklenir. İnternet kapalıysa anlaşılır hata ve tekrar deneme yolu beklenir.
3. **Codex → Hesabımla bağlan**: CLI kurulmalı; resmî ChatGPT girişini siz tamamlamalısınız. Bağlı durumu sonrası yalnız Codex ile sohbete geçilebilmeli.
4. **Gemini → Hesabımla bağlan**: bağımsız agy kurulmalı; Google hesabı girişini siz tamamlamalısınız. Antigravity Desktop/IDE istenmemeli. Giriş tamamlanınca durum güncellenmeli.
5. Her ajana kısa bir normal sohbet mesajı gönderin. Gerçek model yanıtı alınması ayrıca kaydedilmeli; yalnız “Bağlı” model erişiminin kanıtı değildir.
6. Uygulamayı kapatıp yeniden açın. Aynı makinedeki yeni bağlantılar ve sohbet kalmalı; geliştiricinin geçmiş sohbetleri, anahtarları veya projeleri görünmemeli.
7. İki ajan da hazırsa ayrı, zararsız bir test projesinde ana sohbet/Squad kabulü yapılabilir. Bu kurulum çalışması tek başına masaüstü kontrol kabulü sayılmaz.

## Tekrar üretim

```powershell
python -B build.py --require-brand
python -B scripts/prepare_distribution.py <staging> <yeni-temiz-hedef>
./build_installer.ps1 -PackageDir <yeni-temiz-hedef> -Version 2026.10.29
python -B scripts/accept_cli_clean_install.py <izole-klasör> --providers agy codex
```

Kaynak checkpoint ve kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-distribution-20261029`.

## Resmî başvurular

- [Google Antigravity bağımsız CLI kurulumu](https://antigravity.google/docs/getting-started/)
- [Codex hesap ve API anahtarı kimlik doğrulaması](https://learn.chatgpt.com/docs/auth)
- [Microsoft WebView2 dağıtım, tespit ve Evergreen kurulumu](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)

## Son doğrulama ve teslim

| Kontrol | Sonuç | Kanıt |
|---|---|---|
| Tam güvenli regresyon | **576/576 PASS** | `regression-final.log` |
| Kaynak/yürütülebilir paket, giriş kodu, yardımcı, Q simgesi | **45/45 PASS** | `final-package-verification.json` |
| Gerçek agy kurulumu | **VERIFIED**, 1.4.10; yeni özel klasör; SHA-512 + geçerli Google LLC imzası; exit0 | `isolated-install/acceptance.json` |
| Gerçek Codex/Node kurulumu | **VERIFIED**, Codex 0.165.0; önceden CLI/Node keşfi kapalı; exit0 | Aynı dosya |
| Boş mevcut hesap klasöründe Codex durumu | **VERIFIED**, exit1, `Not logged in` | `codex-empty-auth-final.json` |
| İlk Codex hesap denemesi | Fixture klasörü henüz yoktu; yapılandırma hatası, kabul sayılmadı. Klasör oluşturulup yukarıdaki gerçek kontrol yapıldı | `codex-empty-auth.json` |
| WebView2 tespiti | **VERIFIED**, bu makinede 156.0.4314.50 | `webview2-current-status.json` |
| Resmî Evergreen indirme ve imza | **VERIFIED**, 1.889.488 byte, geçerli Microsoft Corporation imzası; kurucu çalıştırılmadı | `webview2-download-check/receipt.json` |
| WebView2 olmayan temiz Windows'ta gerçek kurulum | **NOT TESTED**, mevcut runtime kaldırılmadı | Bir sonraki temiz makine testi |
| Paketlenmiş boş profil ilk açılışı | **UIA VERIFIED**, Hoş Geldiniz, iki CLI kurulacak, üç ajan düğmesi ve Sohbete geç pasif | `gui-test/first-run-uia.txt` |
| Görsel screenshot QA | **BLOCKED**, iki yakalama zaman aşımı | `gui-test/cleanup.json` |
| Yeni kullanıcıyla Google/ChatGPT OAuth tamamlanması ve gerçek model yanıtı | **NOT TESTED**, mevcut kullanıcı oturumları taşınmadı; giriş ekranları otomatik kullanılmadı | Yeni bilgisayardaki kabul adımları |
| Temiz paket | **PASS**, 1.918 dosya, sıfır bulgu | `final-clean-audit.json` |
| Dokuz mevcut kullanıcı dosyası | **diff0** | `preservation-final.json` |

İlk paket gizlilik denetimi iki gerçek bağımlılık CA dosyasını (`certifi/cacert.pem`, `grpc/.../roots.pem`) özel anahtar dosyası gibi reddetti. Yalnız build ortamındaki orijinal public CA dosyalarıyla byte-identical olan bu iki sabit yol için istisna eklendi; farklı PEM ve özel anahtarlar reddedilmeye devam ediyor. Bu, genel bir PEM izin listesi değildir.

Paralel düşük donanım çalışması `gui.py` ve kendi optimizer/test dosyalarını güncelledi. Bu görev optimizer dosyasını düzenlemedi. Eski JS test DOM'unda eksik `document.body` alanı, gerçek arayüz davranışını değiştirmeden test fixture'ına eklendi. Birleşik son kaynak paketle eşleşiyor.

Test kopyasının normal kapatılması `GetCursorPos ... 0x80070005` ile engellendi. Yalnız oluşturduğumuz disposable test EXE'si, PID + EXE yolu + başlangıç zamanı doğrulanarak sonlandırıldı; kendi alt süreçleri temizlendi. Kullanıcının mevcut dağıtımı çalıştırılmadı veya değiştirilmedi. IPC kimlik doğrulaması aşılmadı.

Teslim klasörü: `dist/releases/Quartz-2026.10.29/`.

- `QuartzSetup-2026.10.29.exe`: yeni kurulum.
- `Quartz-2026.10.29-portable.zip`: ayrı taşınabilir paket.
- `SHA256.txt`: iki arşiv/kurucu hash'i.
- `portable/Quartz/release-manifest.json`: dosya bazlı hash envanteri.

Yeni EXE SHA-256: `5f0609722c7732807617873f25f6573005f1f423bc9f63671966a9b37a4c818c`.
Mevcut yerel çalışma EXE'si korunmuştur: `7a1af74c0b59be14c79a426473f23ce4e6d4edcf4781cda4b703e0695a5acaba`.

Quartz/Setup için yayıncı kod imzası eklenmedi. İndirilen üçüncü taraf agy ve Microsoft kurucusunun imza kontrolü bundan ayrı bir kontroldür. Paket çevrimdışı tam kurulum değildir; eksik CLI/runtime indirmeleri için internet gerekir. Google ikilisi bu testte 210.725.528 byte idi.

Karar: **yeni bilgisayarda kurulum kabulüne hazır yerel aday**. Tam temiz Windows kurulumu ve yeni hesapların uçtan uca girişi henüz LIVE VERIFIED değildir. Kamuya upload/release yapılmadı.

Önceki rapordaki Gemini CLI API/masaüstü yolunun geçici system-settings dosyasına ilişkin Windows ACL kabul açığı bu görevde çözülmedi. Google hesap yolu agy kullanır; bu paketin hazırlanması, alternatif API masaüstü yolunu da canlı doğrulanmış yapmaz. Hesap kotası veya sağlayıcının `UNSUPPORTED_CLIENT` gibi erişim kararları yerel kurulum başarısından ayrıdır.
