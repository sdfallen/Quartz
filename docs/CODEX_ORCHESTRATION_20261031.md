# Codex — izin callback ve Stop yaşam döngüsü

Tarih: 31 Ekim 2026. Branch: `codex/orchestration-kernel`.
Kaynak baseline: `59e3533` (üretim kodu referansı `cba9972`).

## Bulgu ve değişiklik

`NaturalDesktopTask.approve` eski veya yinelenmiş izin isteğini doğru biçimde
reddediyor, fakat ortak exception handler mevcut masaüstü bağlantısı varsa
görevi de durduruyordu. Üç ayrı fixture bunu düzeltmeden önce FAILED gösterdi:

- Başarıyla uygulanmış kartın ikinci kez gönderilmesi.
- Geçerli yeni kapsam kartında boolean olmayan onay değeri.
- Yeni kart üretilmişken eski kartın gönderilmesi.

Geçersiz onay hâlâ reddedilir; aktif grant, token, pending kapsam ve görev
korunur. Doğrulanmış isteğin uygulama aşamasında gerçek hata olursa mevcut
fail-closed iptal davranışı korunur.

Bağımsız inceleme, exception handler'ın görev kimliği kontrolü ile Stop'un
başlangıcı arasında yeni görevin açılabildiği bir yarış aralığı belirledi.
`stop(expected_job=...)` görev kimliğini aynı kilit altında kontrol edip
yetkiyi keser. Eski callback yeni görevi iptal edemez.

Stop artık ilk çağrıda yetkiyi keser; overlay/learning release işlemleri bundan
sonra yürür. Tekrarlanan Stop bu kaynakları ikinci kez bırakmaz. Learning
release hata verse de broker/runtime/kanıt temizliği denenir ve hata cleanup
raporuna kaydedilir.

## Sözleşme

- GUI API/payload adları aynı kalır; frontend değişmedi.
- Eski kart başarı olarak dönmez, `PermissionError` ile reddedilir.
- Çift onay tek grant uygular; yeni model turu veya girdi tekrar oynatılmaz.
- Kimlik değişiminde geçerli kartın uygulanması başarısızsa grant iptal edilir.
- Scope, Stop, UAC ve tek operatör politikası korunur.
- Varsayılan `stop(reason)` çağrıları uyumludur; görev kimliği parametresi opsiyoneldir.

## Doğrulama

SOURCE/STATIC: çağrı zinciri ve bağımsız salt okunur kod incelemesi.

TESTED: hedefli NaturalDesktop, elevation, reliability, writer ve izin testleri
101/101 PASS. Sekiz yeni test; callback tekrarı, eşzamanlı onay, kapsam genişlemesi,
gerçek doğrulama hatası, generation değişimi, tekrar Stop ve release hatasını kapsar.
Testler fake desktop ve geçici workspace kullanır.

Tam güvenli regresyon: 677 test case çalıştı; 665 geçti, 12 koşullu fixture
testi SKIPPED. Mevcut `test_q01_q10_review_fixes.py` test sınıfını modül düzeyinde
import ettiği için unittest bu sınıfın testlerini iki kez keşfediyor. Dolayısıyla
sekiz yeni özgün test toplam case sayısını 16 artırdı; 677 bağımsız senaryo
iddiası yapılmaz. Discovery sadeleştirmesi ayrı integration request'tir.

Python sözdizimi: 207 dosya PASS. Gömülü JS: exit0. Staged yayın/geçmiş denetimi:
PASS, bulgu0. CI sonucu PR'da ayrıca kaydedilir. Testler gerçek masaüstü kabulünün
yerine geçmez.

BUILT: NOT TESTED — bu branch'te paket oluşturulmadı.

LIVE VERIFIED: NOT TESTED — paketli ana sohbette gerçek çift onay/Stop kabulü
entegrasyon sonrasında yapılacak. Kurulu Quartz değiştirilmedi.

## Entegrasyon ve kalan iş

Claude'un izin kartı UI kodunu değiştirmesine gerek yok. Frontend kartı ikinci
kez gönderse dahi host aktif görevi korur. Güncel GUI ile entegrasyonda normal
onay, yinelenen kart, kapsam genişlemesi ve kullanıcı Stop'u gerçek paket
üzerinde gözlenmeli. Uzak ajan çalışmaları tamamlanınca birleşik paket ayrı
staging dizininde oluşturulmalı.

ASTER/Warband, kullanıcı verileri, hesaplar, kurulu paket ve performans modülleri
bu değişiklikte düzenlenmedi.
