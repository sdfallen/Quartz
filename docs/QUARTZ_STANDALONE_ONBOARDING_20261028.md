# Bağımsız CLI kurulumu ve ilk bağlantı

## Kullanım

Quartz'ın Codex Desktop veya Antigravity Desktop uygulamalarına ihtiyacı yoktur. Temel çalışma yolu resmî Codex CLI ve Gemini CLI'dır. Önceden var olan bağımsız `agy` kurulumu, mevcut hesap ve model seçimlerini bozmamak için isteğe bağlı olarak kullanılabilir.

Bağlı bir CLI yoksa ilk açılışta **Quartz'a Hoş Geldiniz** görünür. Kullanıcı Codex veya Gemini seçip **Hesabımla bağlan** ya da **Doğrula ve bağlan** seçeneğini kullanır. Eksik CLI o işlem sırasında arka planda otomatik kurulur. Yalnız bir sağlayıcı yeterlidir; diğeri ve Birlikte seçeneği pasif gösterilir. **Hesaplar ve CLI kurulumu** düğmesi akışı yeniden açar. İnternetsiz durumda hata gösterilir, yeniden deneme mümkündür.

Hesap girişi resmî CLI'nın kendi giriş penceresinde/Google tarayıcı akışında kullanıcı tarafından tamamlanır. Quartz parola veya doğrulama kodu toplamaz. API anahtarı yolu `/models` isteğiyle doğrulanır; bu, ilgili tüm modellerde kota/üretim erişimi garantisi değildir. Hesap aboneliği ile API kullanım bedeli ayrı seçeneklerdir.

## Dosyalar ve sınırlar

- `core/cli_installer.py`: açık yol, Quartz bin klasörü, özel kurulum manifesti ve PATH üzerinden keşif. Eksik runtime için Node'un resmî LTS Windows ZIP'i ve SHA256 doğrulaması. Resmî npm registry'sinden tam sürüme sabitlenen `@openai/codex` / `@google/gemini-cli`; global npm kurulumu yok. npm integrity kontrolü ve CLI `--version` başarılı olmadan manifest yayımlanmaz.
- Kurulum yeri `%LOCALAPPDATA%\Quartz\bin`; `QUARTZ_CLI_ROOT` ile izole test klasörü seçilebilir. PATH yalnız CLI çocuk sürecinin ortamına eklenir. Registry veya kalıcı Windows PATH ayarı değiştirilmez. npm kurulum scriptleri çalıştırılmaz (`--ignore-scripts`).
- CLI giriş dosyası paketin `package.json/bin` tanımından okunur; paket içinden çıkabilecek yol reddedilir. Model metni Node'a argüman listesiyle veya Codex'e stdin ile gönderilir.
- `core/gemini_runtime.py`: Gemini stream-json olaylarını mevcut Quartz run/lifecycle sözleşmesine çevirir. Antigravity oturum kimlikleri Gemini resume kimliği olarak kullanılmaz. Gemini düşünme seviyesi otomatik olduğundan CLI'ya uydurma `--effort` bayrağı gönderilmez.
- Gemini'nin masaüstü oturumunda yalnız Quartz MCP araçları açık; terminal/dosya araçları core allowlist ile kapalıdır. MCP bearer yalnız süreç ortamındadır, ayar dosyasında ortam referansı bulunur. Ayarlar çocuk sürece özel geçici dosyadır; kullanıcı Gemini ayarları değiştirilmez. Üretim model araç çağrısı bu değişiklik için henüz canlı doğrulanmış değildir.
- `core/onboarding.py`: uzun kurulum işi arka planda, durum sorguları önbellekli. Doğrulanmamış anahtar diske yazılmaz. Anahtar yalnız `.env` içinde saklanır. `quartz_memory.json` içinde yalnız bağlantı yöntemi ve tarih vardır. Dosyalar tek tek atomik değiştirilir; metadata yazma hatasında `.env` geri alınır. Ani güç kaybında `.env` bağlantı için esas kaynaktır; iki farklı dosya için dosya sistemi düzeyinde ortak transaction iddiası yoktur.
- `gui.py`, `main.py`: Türkçe onboarding, durum, kurulum/bağlantı işlemleri ve bağlı runtime'ları yenileme. Tek ajanla genel sohbet kullanılabilir; eksik gözlemci bir masaüstü operatörünü durdurmaz. Mevcut Full tercihi değiştirilmedi.
- `assets/bin/squad.exe`: mevcut MIT lisanslı Squad 0.7.6 yardımcısı lisans/provenance kaydıyla pakete dahildir. `core/squad_adapter.py` paket içi yolu bulur; yeni kullanıcıya `C:\squad` kurulumu gerekmez. Yalnız Windows x64 ikilisi bu pakette doğrulandı; diğer mimariler için ayrıca paket kabulü gerekir.
- `.env.example`: isteğe bağlı OpenAI/Gemini değişkenleri. Ücretli API anahtarına sessiz geçiş yoktur.

## Kanıtlar

Kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-onboarding-20261028`.

- Ön kaynak checkpoint: `agent-1793192607-5de011bac43f466fba3559192e273622.zip`, Git snapshot `b5fdd0f21ff019f7b5160f775a5d3d2469f06275`.
- `full-final.log`: 500/500 PASS. Paralel düşük donanım değişiklikleriyle birlikte `merged-final.log` ve `final-source-regression.log`: 505/505 PASS. Gömülü JavaScript sözdizimi kontrolü PASS.
- `delivery-regression.log`: Squad paket keşfi dahil 506/506 PASS. `standalone-squad/acceptance.json`: pakete alınan gerçek ikiliyle disposable yerel workspace init/join/send/receive PASS. Gerçek dış ajan görevi gönderilmedi.
- `clean-install/acceptance.json`: gerçek Node/npm kurulumu ve `--version` işlemleri. İlk keşifte PATH CLI'ları ve Desktop uygulama yolları kullanılmadı. Codex 0.165.0 ve Gemini CLI 0.66.0 bağımsız kuruldu/açıldı. Bu bir temiz Windows VM kabulü değildir; mevcut Windows üzerinde izole ortam testidir.
- İlk gerçek Gemini denemesi FAILED: sabit `dist/index.js` yolu güncel pakette yoktu. Paket `bin` alanı kullanılarak düzeltildi; sonraki gerçek kurulum PASS. Önceki başarısızlık `clean-install.log` içinde korundu.
- `tests/test_cli_installer.py`: keşif, PATH koruma, checksum, arşiv kaçışı, kurulum hatası ve manifestin yalnız başarılı doğrulama sonrası yazılması.
- `tests/test_onboarding.py`: tek sağlayıcı, yanlış anahtarda sıfır kayıt, metadata koruma, yazma hatasında rollback, anahtarın argv'ye sızmaması, Gemini protokolü ve Desktop'sız fallback.
- Gömülü JS sözdizimi kontrolü PASS. Gerçek API anahtarı/hesap girişini tamamlama ve yeni Gemini backend ile ücret/kota tüketen model görevi bu test kapsamında yapılmadı.

Paket ve arayüz kabul durumu ayrıca teslim makbuzuyla ilişkilendirilmelidir. Önceki kullanıcı kaynak değişiklikleri, Antigravity'nin düşük donanım çalışması ve mevcut kullanıcı verileri korunur. ASTER/Warband'a dokunulmadı.

İlk iki paket kontrolü yalnız `main.py` için kaynak farkı bildirdi: paralel değişiklik ve analiz sırasında eklenen son oturum kontrolü derleme önbelleğinde eski kalmıştı. Bu paketler teslim edilmedi. `source-freeze.json` sonrası yeni bir temiz PyInstaller çalışma klasörüyle paket doğrulaması yenilendi; `build-clean.log` ve son paket makbuzu esas alınmalıdır.

## Resmî referanslar

- Codex CLI: https://developers.openai.com/codex/cli
- Codex hesap/API anahtarı girişi: https://developers.openai.com/codex/auth
- Gemini kurulumu: https://geminicli.com/docs/get-started/installation/
- Gemini kimlik doğrulaması: https://geminicli.com/docs/get-started/authentication/
- Gemini headless protokolü: https://geminicli.com/docs/cli/headless/
- Gemini süreç ayarları/core araç listesi: https://geminicli.com/docs/reference/configuration/

## Son teslim durumu

- Son kaynak regresyonu: `regression-login-discovery.log`, **507/507 PASS**. Farklı PATH ile mevcut Codex oturumunun keşfi ayrıca `path-independent-login.json` içinde doğrulandı.
- Son kurulu EXE: `742ee41461e94fcfac6ec5c21b76ea4fc201a880ccc8eb35391f93b11c6e6e69`. `installed-verification-sol.json` kaynak/paket eşleşmesini kaydeder. Son dağıtım makbuzu `deployment-receipt.json`.
- Boş `.env`, boş kullanıcı profili, sınırlı PATH ile gerçek paketli Quartz çalıştırıldı (test PID 25956). `clean-onboarding-uia.txt`: Hoş Geldiniz modalı, Codex/Gemini seçimi, hesap girişi/API anahtarı seçenekleri, anahtar alanı ve bağlantı yokken pasif Sohbete geç düğmesi **UIA üzerinden doğrulandı**. Bu, ekran görüntüsüyle görsel kalite onayı değildir.
- Ekran aracı `foreground window did not report a process id` ve `window capture timed out` verdi. Normal kapatma girdisi kullanıcı girdisi korumasına takıldı; koruma aşılmadı. Sonraki süreç kontrolünde test Quartz'ı kapalıydı. Test profili kullanıcı profilinden ayrı kaldı.
- `preservation-after.json`: dokuz korunan kaynak/kurulum ayar, sohbet, proje ve bellek dosyası **hash-equal**. Önceki dağıtım `quartz-before-desktop-bridge-20261028-170908` altında korunur.
- **Kalan gerçek kabul:** yeni kullanıcıyla resmî hesap girişini veya gerçek anahtar doğrulamasını tamamlamak, ardından yeni Gemini CLI backend'iyle bir gerçek model/masaüstü görevi. Bu adımlar mock veya sürüm kontrolünden LIVE VERIFIED olarak çıkarılmadı. Temiz Windows VM kabulü ve görsel screenshot QA ayrıca yapılmadı.

Son normal profil açılışı: kurulu yeni EXE 28 Ekim 2026 17:11'de başlatıldı (PID 25068). `final-normal-profile-uia.txt`: mevcut sohbet, seçili modeller, Tam Yetki ve Codex/Antigravity/Birlikte düğmelerinin etkin durumu gözlemlendi. Kullanıcı kapattığını onayladıktan sonra normal profil açıldı; test profilinde hesap girişi başlatılmadı.
