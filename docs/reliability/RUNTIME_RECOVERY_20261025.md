# Süreç uzlaştırması ve kontrollü devam — 25 Ekim 2026

Başlangıç: `9e5d5c9`, dal `codex/reliability-kernel-20261025`.
Pre-change checkpoint:
`C:/Users/LENAVO/.codex/backups/quartz-runtime-recovery-20261025/agent-1792921019-0df4ea49f3774bfeb371d13fb80ff8b2.zip`.

## Dar mimari değişiklikler

`WriterJournal`, mevcut MultiAgentService yazıcı kabulünün küçük bir disk
sözleşmesidir. Yeni task motoru/registry değildir. Kurulu uygulamada
`.quartz/writer_claims.json` kullanılır. Explicit store yolu verilmemiş, geçici
headless/library örnekleri önceki geçici davranışı korur. Aynı garanti istenen
harici istemci aynı journal yolunu açıkça kullanmalıdır.

```text
OS dosya kilidi + kalıcı rezervasyon
  -> doğrulanmış checkpoint
  -> starting kaydı -> runtime start -> PID/create-time/EXE gözlemi
  -> gerçek terminal sonuç + süreç kontrolü
  -> kaynak receipt -> kalıcı rezervasyonu bırakma

Start sonucu / süreç gözlemi belirsizse:
  rezervasyon korunur -> çakışan yeni yazma engellenir -> açık inceleme gerekir
```

- PID tek başına sahiplik kanıtı sayılmaz. PID tekrar kullanımı, yol farkı ve
  okunamayan süreçler ayrı değerlendirilir. Kayıtlı canlı veya okunamayan
  gözlenmiş süreç varken kullanıcı onayı bile engeli aşmaz.
- Ana PID'nin yokluğu bütün alt süreçlerin bittiğini kanıtlamaz. Kaydı kaldırmak
  için dış süreç/dosya incelemesi ve ayrı açık onay gerekir. İnceleme kaydı
  ayrıca arşivlenir; eski iş, session veya izin geri yüklenmez. Otomatik kill yok.
- Proje/alt-proje çakışmaları ve full-access kapsamı korunur. Süreye göre eski
  kilidi tahminen kaldırma yok. OS-held nonblocking dosya kilidi iki facade'ın
  aynı eski JSON'a göre eşzamanlı rezervasyon yapmasını engeller.
- Bozuk JSON, yazma/okuma hatası ve eksik checkpoint fail-closed davranır.
  Başlama çağrısı sonrasında hata varsa süreç oluşmadığı varsayılmaz.
- Normal app kapanışı iki runtime cleanup'ını ayrı dener ve kendi sonlandırma
  gözlemcilerine toplam en fazla 3 saniye settle fırsatı verir. Terminal etiketi,
  gözlenen hâlâ canlı writer sürecini serbest bırakmak için yeterli değildir.
- Masaüstü broker'ına yalnız GUI tarafından bağlanan admission veto eklendi.
  Yetki açmaz; ana sohbet, legacy adaptör ve Natural akışlarının ortak grant
  noktasında çözülmemiş writer durumunu kontrol eder. Bu karar öncesi journal
  kilitli dosyadan taze okunur; UI polling önbelleği yetki kararı vermez.

## Kontrollü devam

Kesilmiş mesajdaki **Yeni görev taslağı hazırla** düğmesi orijinal kullanıcı
isteğini okur, ayrı ve provider session'ları boş bir sohbet açar, işlem düzeyini
salt-okunura indirip eski write-confirmed bayrağını sıfırlar. Metni taslak olarak
yerleştirir; otomatik send/dispatch yoktur. Kullanıcı önce gerçek uygulama ve
dosya durumunu incelemeli, sonra yeni görevi göndermelidir. Gerekli desktop ve
yazma izinleri normal yeni görev akışından tekrar alınır.

Bu akış checkpoint'i otomatik geri yüklemez, yarım kalan işlemi körlemesine
tekrarlamaz ve tarihsel model çıktısını güvenilir talimat/otorite yapmaz.

## Ajan başına ilerleme

Codex/Antigravity için ayrı message/run kimliği, aşama, durum ve timestamp
tutulur. Eski turun callback'i yeni turu değiştiremez; eski balon yeni aynı-ajan
balonunun progress'ini çalamaz. Son genel scalar alan uyumluluk için kalır;
UI durum metni iki ajanı birlikte gösterir. F05 kontratı expectedFailure'dan
normal regresyon testine yükseltildi. Eski bağımsız rapor tarihsel olarak korunur.

## Kanıtlar ve sınırlar

| Alan | Kanıt / kapsam |
|---|---|
| Gerçek ayrı süreç | `labs/runtime-journal-20261025-125905/result.json`: producer kapandı, kendi sleep çocuğu canlı kaldı, yeni yazma ve erken onay engellendi; doğal çıkış sonrası açık review/arşiv akışı çalıştı. 9 kontrol VERIFIED. Hiçbir süreç öldürülmedi. |
| Gerçek dosya yazıcısı | `labs/reliability-writer-20261025-125451/result.json`: Codex geçici authored fixture'da bir dosya düzeltti; test dosyası değişmedi, iki test host'ta ayrıca geçti; checkpoint/receipt/writer ve durable claim bırakma VERIFIED. |
| Gerçek iki CLI | `labs/reliability-live-20261025-125542/result.json`: iki sağlayıcı, sıfır araç olayı, iki bağımsız completed progress kaydı VERIFIED. GUI kabulü değil. |
| Son delta | Yetki öncesi read-only journal refresh sonradan sertleştirildi; ilgili OS lock/read ve coroutine/JS testleri geçti, gerçek ayrı süreç probe tekrarlandı. CLI writer/text yolu için sonuçlar yukarıdaki aynı dilim koşularıdır, bütün GUI'nin yeni canlı kabulü olarak taşınmaz. |
| JavaScript | İki progress etiketi, interrupted draft düğmesinin yeni sohbet açıp read-only yapması ve send çağırmaması gerçek JS VM içinde test edildi. Rendered visual QA değil. |

Son dağıtım kapısı: **451 test = 449 PASS + 2 expectedFailure**, beklenmeyen
failure/error yok (52.223 s). JavaScript syntax ve secret/history audit PASS.
34 paket/source/helper/ikon kontrolünün tamamı PASS. Kurulu EXE SHA256:
`76013abf5c2f0c7871130290d0fec210b9443b6220b84f060a5634b0bafd2421`.
Alındı: `C:/Users/LENAVO/.codex/backups/quartz-orphan-package-20261025/deployment-receipt.json`.
Eski dağıtım: `C:/Users/LENAVO/.codex/backups/quartz-before-desktop-bridge-20261025-130349`.
Başarılı kod/parity doğrulaması görsel acceptance değildir.

Yeni paket gerçek Windows penceresinde açıldı; UIA mevcut proje, salt-okunur
işlem düzeyi, Gemini 3.8 Flash High ve GPT-6-Sol seçimlerini gösterdi. Görsel
yakalama, pencere bağını yenileyerek bir retry dahil iki kez
`window capture timed out: timed out waiting on channel` ile başarısız oldu.
Kullanıcının son bildirdiği kapalı ekran/uzak oturum koşulunu değiştirmedik;
kesin kök neden veya düzeltilmiş Quartz capture bug'ı ilan edilmedi. GUI görevi
başlatılmadı, draft/review/izin kartları otomatik tıklanmadı. Bu yeni UI'nin
gerçek görsel ve input kabulü **BLOCKED**; JS VM sonuçları bunun yerine geçmez.
Kendi Quartz penceresi normal Alt+F4 ile kapandı; süreç ve pencere yokluğu
ayrıca doğrulandı. Kurulu `.env`, mobile access, sohbet, hafıza ve proje JSON'ları;
kök `.env`, sohbet ve hafıza dosyaları alındıya göre hash-eşit kaldı. Runtime
logları normal çalışmada değişebilir; onlar için değişmedi iddiası yoktur.
İki kalan expectedFailure, tek kullanımlı NaturalTask nesnesini yeniden kullanma
ve teknik ayrıntılardan da ham neden metnini kaldırma önerileridir. Bilinçli
korunan sözleşmelerle çeliştikleri için kritik bug sayılmadı veya sahte PASS
yapılmadı.

## Bilinen sınırlar

- Orphan süreçler otomatik sonlandırılmaz. Kayıtlı süreç canlı/okunamıyorsa önce
  onun gerçek durumu çözülmelidir. Starting anında PID kaydı oluşmadan kapanma
  gibi belirsizlikler dış inceleme olmadan silinmez.
- Aynı app session'ının belirsiz yazıcı kaydı normal insan-review akışından
  bırakılamaz; kontrollü kapanış ve yeni oturum incelemesi gerekir. Bu, hâlâ
  çalışan mevcut görevden bir güvenlik kilidini sökmemek içindir.
- Daha önce journal kullanmadan başlamış süreçlere geriye dönük sahiplik
  uydurulmaz. Root PID kaybından tüm alt süreçlerin bittiği sonucu çıkarılmaz.
- Uçtan uca paketli ana sohbet/masaüstü görüntülü kabul henüz BLOCKED.
  Son bilinen koşul kapalı ekran/uzak oturum; bu test aracı timeout'unun kesin
  kök nedeni diye gösterilmez. Görsel erişim/izin engeli aşılmaz, rastgele tıklama
  yapılmaz. Kaynak/JS/CLI/process sonuçları görsel kabulün yerine geçmez.
- Büyük legacy framework birleştirmesi, otomatik crash replay, WSE2 veya yeni
  runtime eklenmedi. Mevcut adaptörler ortak grant veto ve sonuç sözleşmesiyle
  korunur; doğrulanmış iş akışları bir kerede yeniden yazılmaz.

ASTER/Warband, kayıtlar, Overlay, registry/sürücü/güvenlik ayarları ve mevcut
kullanıcı model seçimi bu geliştirmede değiştirilmeyecek. GitHub push yok.
