# Quartz — Gerçek Google bağlantı teşhisi ve Antigravity CLI geçişi

Tarih: 29 Ekim 2026.

## Gerçek nedenler

1. Önceki OAuth düzeltmesinde, geçerli CLI girişinin ilk doğrulaması ek bir tıklamaya bağlı kalmıştı. Giriş işlemi tamamlandığında arayüzün sorgulaması da erken durabiliyordu. Bu durum düzeltildi: geçerli token otomatik kontrol edilir, süresi geçmiş token hazır sayılmaz, devam eden girişte eski “bağlı değil” önbelleği kullanılmaz.
2. Gerçek model çağrısı ek bir sağlayıcı engelini ortaya çıkardı. Google UserInfo **HTTP 200** döndürdü; ancak Gemini CLI model başlangıcında **`UNSUPPORTED_CLIENT` / `IneligibleTierError`** ile bu bireysel hesabı reddetti. Kurulu `@google/gemini-cli 0.66.0`, kontrol anındaki resmî npm `latest` sürümüyle aynıydı. Bu koşu için sorun yanlış parola veya quota hatası olarak sınıflandırılmadı.
3. Windows CLI tanısında, üst PowerShell 7 ortamından gelen modül sırası Windows PowerShell'in `Get-Acl` modülünü yüklemesini engelledi. Yalnız alt süreçte yerel Windows modül yolu öne alındı; gerçek salt okunur Get-Acl sorgusu böylece çalıştı. Sonraki CLI kontrolü, geçici sistem ayarının normal kullanıcıya ait olması nedeniyle ayrıca reddedildiğini gösterdi. **Bu ikinci ACL sahipliği kuralı aşılmadı veya kapatılmadı.** Gemini CLI'nin bu Windows sistem-ayar adaptörü bu oturumda canlı kabul edilmiş sayılmıyor; doğrulanan Google yolu bağımsız Antigravity CLI'dir.

Google hesabının doğrulanması, her istemcinin/modelin o hesap için kullanılabildiği anlamına gelmez. Önceki rapordaki SOURCE/TEST sonuçları bu canlı engeli kapsamıyordu.

## Kullanıcının onayladığı yol

Kullanıcı Google ajanını kurulu ve bağlı **Antigravity CLI (`agy`)** üzerinden çalıştırmayı açıkça onayladı.

- Antigravity Desktop kurulmadı ve zorunlu hâle getirilmedi.
- API anahtarına veya API faturalanmasına sessiz geçiş yapılmadı.
- Gemini CLI API-key yolu korunuyor. Açıkça seçilmiş Gemini CLI, çalışma anında gizlice başka backend'e yönlendirilmiyor.
- Google hesap bağlantı düğmesi artık önerilen bağımsız Antigravity CLI yolunu açıklar.
- `account_agy` bağlantı işlemi, hazır mevcut CLI hesabını tekrar giriş veya Gemini npm kurulumu yapmadan kullanır.
- `backend=agy, method=account` seçimi, ortamda Gemini API anahtarı bulunsa da korunur.
- CLI yoksa anlaşılır hata verilir; **bu değişiklik yeni bilgisayara otomatik agy indirme motoru eklemez**. Bu makinedeki mevcut resmî CLI kullanılmıştır.

## Gerçek model kanıtı

İzole geçici dizinde, kullanıcı projesine erişmeden:

| Alan | Sonuç |
|---|---|
| İstemci | Antigravity CLI 1.4.10 |
| Hesap yöntemi | Google hesabı |
| Model | `gemini-4-argon-medium` |
| Quartz runtime sonucu | `completed` |
| Native exit code | 0 |
| Gerçek model yanıtı | `QUARTZ_GOOGLE_OK` |
| Hata | Yok |

Bu kanıt gerçek runtime/model çağrısıdır; paketli ana sohbetten iki ajanlı masaüstü görevinin kabulü değildir. Bu oturumda kullanıcı adına YouTube veya ASTER görevi başlatılmadı.

## Kaynak değişiklikleri

- `core/gemini_auth.py`: ilk geçerli token kontrolü otomatik, başarısız kontrol için kısa cache, Windows alt süreç modül yolu.
- `core/onboarding.py`: devam eden hesap girişinde cache/sorgulama, açık `account_agy` işlemi ve hazır hesabı kullanma.
- `core/gemini_runtime.py`: açık Antigravity hesap tercihini API ortamından önce uygulama.
- `gui.py`: gerçek backend adı, devam eden girişte sorgulamayı sürdürme ve açık Google hesap bağlantısı.
- `main.py`: Gemini oturum/modelini Antigravity bağlantısına yanlışlıkla taşımama; yeniden açılıştaki `auto` modelini düzeltme.
- Regresyonlar: `tests/test_gemini_auth_selection.py`, `tests/test_gui_connection_polling.py`.

Kaynak, gerçek model ve paket/arayıcı doğrulamaları birbirinden ayrı tutulur.

## Kanıtlar ve koruma

Kök: `C:\Users\LENAVO\.codex\backups\quartz-gemini-connection-20261029`.

- `checkpoint-before.json`: değişiklik öncesi tam kaynak checkpoint'i.
- `data-before.json`: kullanıcı dosyalarının başlangıç hash'leri.
- `live-model-diagnostic.json`: Gemini CLI'nin gerçek reddi; token değerleri kayda alınmadı.
- `live-agy.json`: gerçek başarılı Antigravity model çağrısı.
- `source-freeze.json`: son paket için kaynak hash'leri.
- `labs/gemini-connection-20261029/`: hedefli testler, paketleme ve yayın denetimi kayıtları.

İlk paket kontrolü `main` modülünün son oturum düzeltmesiyle eşleşmediğini gösterdi. Bu paket teslim edilmedi; kaynak sabitlenip yeniden derlendi. Nihai paket kontrolü ve veri karşılaştırması teslim kaydında ayrıca tutulur.

Yeni bağlantı tercihi ve gerekiyorsa uyumsuz model/oturum alanları bilinçli olarak güncellenir. Sohbet metinlerinin korunması ayrıca karşılaştırılır; bu beklenen ayar değişikliği “bütün dosyalar diff0” diye sunulmaz. API anahtarları, ASTER ve oyun kayıtları korunur.

## Nihai teslim

- Tam son regresyon: **557 PASS**.
- Kaynaklar sabitken temiz Python/PyInstaller önbelleğiyle derleme yapıldı; bütün paket eşleşmeleri PASS. Önceki artımlı pakette kalan eski `main` kodu teslim edilmedi.
- EXE SHA-256: `7a1af74c0b59be14c79a426473f23ce4e6d4edcf4781cda4b703e0695a5acaba`.
- Önceki paket: `C:\Users\LENAVO\.codex\backups\quartz-before-desktop-bridge-20261029-161448`.
- Kullanıcının onayıyla `backend=agy` uygulandı; **ready=true** gerçek runtime probe'uyla doğrulandı.
- Bir uyumsuz `auto` model seçimi, gerçek çağrıda çalışan `gemini-4-argon-medium` seçimine taşındı. Diğer geçerli model seçimleri korunur.
- Mesaj listeleri, diğer hafıza alanları, diğer bağlantılar ve API ayar dosyası karşılaştırmada eşit. Yalnız onaylı Google bağlantı metadata'sı ve uyumsuz model/oturum ayarları değişti.
- Quartz normal kapatılıp yeni sürümle açıldı. Gerçek UIA gözleminde **ÇEVRİMİÇİ**, etkin **Antigravity** ve **Birlikte** düğmeleri ile yeni model seçimi görüldü.
- Gerçek paketli ana sohbetten yeni kullanıcı mesajı gönderilmedi; bu inceleme mevcut kullanıcı sohbetine test mesajı eklemedi.

Ek kanıtlar: aynı yedek kökünde `deployment-receipt.json`, `package-verification.json`, `regression-final.log`, `approved-migration.json`, `data-after-migration.json`, `live-uia.txt`.

## Birincil referanslar

- [Google Gemini CLI deposundaki aynı OAuth/UNSUPPORTED_CLIENT raporu](https://github.com/google-gemini/gemini-cli/issues/28846)
- [Gemini CLI resmî kimlik doğrulama belgeleri](https://geminicli.com/docs/get-started/authentication/)

Genel bir “bütün hesaplar için Gemini CLI çalışmaz” iddiası yapılmıyor. Bu makinede bu hesapla alınan sunucu reddi esas alındı.
