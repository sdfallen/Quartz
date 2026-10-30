# Quartz — Gemini seçim ve OAuth doğrulama düzeltmesi

Tarih: 29 Ekim 2026.

## Kapsam

`QUARTZ_KONTROL_20261029.md` içindeki üç tekrar üretilebilir açık düzeltildi:

1. `google_runtime()` artık `base` verilmediğinde de gerçek uygulama kökünden kayıtlı Gemini tercihini okur. Normal servis çağrısı sessizce eski agy yoluna düşmez.
2. Hesap yöntemi seçildiğinde hem giriş süreci hem sonraki görev alt süreci hesap yöntemini kullanır. API/Vertex ortam değişkenleri yalnız alt süreç kopyasından çıkarılır; kullanıcının `.env`, sistem ortamı veya sağlayıcı ayar dosyaları silinmez/değiştirilmez. Çocuk sürece özel CLI ayarında `oauth-personal` seçilir ve proje `.env` yüklemesi kapatılır.
3. OAuth dosyasının bulunması veya token alanının dolu olması doğrulama sayılmaz. Süresi geçmiş/bozuk/henüz kontrol edilmemiş kayıt hazır gösterilmez.

## OAuth kontrol sözleşmesi

- İlk hesap doğrulaması, **Bağlantıyı kontrol et** üzerinden yapılır.
- Google'ın UserInfo endpoint'ine HTTPS isteği kullanılır; token URL'ye yazılmaz, Authorization başlığında gönderilir. Yönlendirmeler reddedilir; timeout 5 saniyedir.
- Bu kontrol bir model üretim isteği değildir. Model erişimi/kotası için başarı iddiası üretmez.
- Token süresi doğrulanmadan uzaktaki kontrol yapılmaz. Token yenilemeyi Quartz kendisi üstlenmez; resmî CLI girişinin yenilenmesi istenir.
- Başarılı kontrolün kısa süreli önbelleği token dosyası parmak izine bağlıdır. Yalnız parmak izi, zaman ve sonuç saklanır; token veya kullanıcı profili saklanmaz.
- Daha önce doğrulanmış oturumun cache'i eskirse veya token değişirse eski başarılı sonuç doğrudan tekrar kullanılmaz; yeniden kontrol edilir.
- Seçilen yöntem runtime probe'unun önbellek kimliğine de dahil edilir; API ile hesap durumu birbirine aktarılmaz.

## Dosyalar

| Dosya | Değişiklik |
|---|---|
| `core/gemini_auth.py` | Ortak seçim, süreç ortamı ve OAuth kontrolü |
| `core/gemini_runtime.py` | Varsayılan metadata okuma, seçilen yöntemle görev ve doğru probe/cache |
| `core/onboarding.py` | Hesap durumunu gerçek doğrulama sonucuna bağlama, giriş alt süreci için hesap ayarı |
| `gui.py` | “Bağlantı doğrulanmalı” ve anlaşılır hesap kontrolü açıklaması |
| `tests/test_gemini_auth_selection.py` | Normal çağrı ve kimlik doğrulama regresyonları |
| `tests/test_onboarding.py` | Eski factory testlerini kullanıcının gerçek metadata'sından izole etme |
| `scripts/verify_desktop_package.py` | Yeni ortak auth modülünü paket eşleşmesine dahil etme |

## Doğrulama

- İlk beş regresyon: değişiklik öncesi **5/5 FAIL**; gerçek açıkları gösterdi.
- Genişletilmiş odaklı test grubu: **54 PASS**.
- Paketleme öncesi tam güvenli test grubu: **550 PASS**.
- Gömülü JavaScript kontrolü: PASS.
- Yayın denetimi: PASS, bulgu 0.
- Gerçek hesapla OAuth/model görevi: **NOT TESTED**. Testlerde örnek tokenlar ve sahte HTTP yanıtları kullanıldı.
- Gerçek paketli GUI'de hesap girişinin uçtan uca kabulü: **NOT TESTED**.

## Paket teslimi

- Yeni EXE `dist/Quartz/Quartz.exe` konumuna yerleştirildi; uygulama kapalıydı ve otomatik başlatılmadı.
- SHA-256: `c3d3fc11dcafc8ab562055314462a259bb404f82ec3bf96d1ad0ab8a9d6f2673`.
- Paketleme ve teslim öncesi kontrol edilen bütün modüller, yeni `core.gemini_auth` dahil, kaynakla eşleşti. Yardımcı araç protokolü ve yetkisiz gözlemde güvenli ret testi de geçti.
- Standart teslim aracının zorunlu son regresyonu: **550 PASS**.
- Kaynak/paket tarafındaki dokuz kullanıcı veri dosyası son karşılaştırmada **9/9 eşit**. Teslim aracının koruduğu paket verileri de eşit.
- Önceki paket: `C:\Users\LENAVO\.codex\backups\quartz-before-desktop-bridge-20261029-142836`.
- Teslim makbuzu: `C:\Users\LENAVO\.codex\backups\quartz-auth-fix-20261029\deployment-receipt.json`.

Kaynak ve paket testlerinden gerçek hesap/GUI kabul sonucu çıkarılmaz.

## Kanıt ve koruma

- `labs/gemini-auth-fix-20261029/before.log`
- `labs/gemini-auth-fix-20261029/focused.log`
- `labs/gemini-auth-fix-20261029/build.log`
- `labs/gemini-auth-fix-20261029/publish-audit.json`
- Yedek/ön checkpoint: `C:\Users\LENAVO\.codex\backups\quartz-auth-fix-20261029\checkpoint-before.json`.
- Aynı yedek klasöründe bu oturuma özgü `changes.patch` ve kullanıcı veri hash manifestleri.

Kullanıcının Full yetki tercihi, sohbetleri ve proje ayarları korunur. ASTER/Warband ve oyun kayıtlarına dokunulmaz. Önceki diğer geliştirici değişiklikleri geri alınmaz.

## Resmî referanslar

- [Gemini CLI kimlik doğrulaması](https://geminicli.com/docs/get-started/authentication/)
- [Google OpenID Connect — UserInfo ve Authorization başlığı](https://developers.google.com/identity/openid-connect/openid-connect#obtaininguserprofileinformation)
