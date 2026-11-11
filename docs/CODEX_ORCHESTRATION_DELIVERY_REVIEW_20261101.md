# Quartz paralel teslim incelemesi

Tarih: 1 Kasım 2026 (Europe/Istanbul). İnceleme başlangıcı 31 Ekim gecesi.
Kapsam: teslim/ownership, kaynak diff'i, Windows testleri, kontrollü hata
tekrarları. Bu çalışma üretim kaynaklarını düzeltmez, PR birleştirmez ve kurulu
Quartz paketini değiştirmez.

## Karar

| Teslim | İncelenen commit | Sonuç |
|---|---|---|
| Codex PR #2 | `b72493e7ed17d12da134756c85fe9300841fa468` | Kaynak/test kabulüne hazır; paketli sohbet kabulü bekliyor |
| Claude PR #3 | `e690878cfc5a309beafd32176b8e4b7b3677a975` | İlk frontend ayrıştırma dilimi kaynak/test açısından uygun |
| Antigravity PR #4 | `44fdff31542cac435599514ed43a1d5b3b792be8` | REQUEST CHANGES önerisi; aşağıdaki P1 sorunlar giderilmeli |
| Notion / Kimi | Teslim branch/PR'ı yok | Kullanıcı bildirimi: GitHub bağlantısı yok; görev BLOCKED, incelenmiş sayılmaz |

PR'lar: <https://github.com/sdfallen/Quartz/pull/2>,
<https://github.com/sdfallen/Quartz/pull/3>,
<https://github.com/sdfallen/Quartz/pull/4>.

REQUEST CHANGES bu yerel raporun hükmüdür; GitHub'a review/yorum gönderilmedi.

## Doğrulanan bulgular

### A-01 — P1: Watchdog eski sorgunun güncel sonucu ezmesine izin veriyor

Konum: PR #4 `core/async_snapshot.py:38–43`, `:73–80`.

Timeout'ta yalnız `self.worker = None` yapılıyor. Eski thread devam ediyor ve
aynı proje için `generation` değişmiyor. Yeni thread'in ardından eski thread
tamamlanırsa aynı generation kontrolünü geçip eski veriyi yayımlıyor. Ayrıca
eski thread yenisinin worker referansını temizleyebiliyor. Her timeout'ta yeni
thread açılması, loader gerçekten takıldığında birikmeyi sınırlamıyor.

Kontrollü ölçüm (gerçek Python thread'leri, Event ve sahte saat; model/ağ/UI yok):

```json
{"before_old_completion":{"attempt":2},
 "after_old_completion":{"attempt":1},
 "stale_overwrite":true,"loader_attempts":2}
```

Öneri: proje generation'ına ek attempt/worker kimliğiyle geç gelen sonucu
geçersiz kıl. Terk edilen thread'lerin sayısı için gerçek sınır koy veya worker
bitene kadar tek-uçuş davranışını koru. Test yalnız yeni thread açıldığını değil,
eski thread'in yeni sonucu ezemediğini ve eşzamanlı probe sayısının sınırlı
kaldığını doğrulamalı.

### A-02 — P1: Süreç ağacı keşfi reddedilince Stop çalışan süreci bırakıyor

Konum: PR #4 `core/process_tree.py:51–55`, `:87–93`.

`parent.children(recursive=True)` AccessDenied verirse kod hem parent'ı hem
descendants listesini boşaltıyor. Sahip olunan Popen için terminate/kill
fallback'i kalmamış; kısa wait hatası da yutularak işlev geri dönebiliyor.
Baseline bu hata yolunda sahip olduğu Popen üzerinden sonlandırmayı deniyordu.

Sadece mock süreç nesneleriyle ölçüm (hiçbir gerçek süreç öldürülmedi):

```json
{"owned_terminate_calls":0,"owned_kill_calls":0,
 "psutil_parent_terminate_calls":0,"returned_with_process_alive":true}
```

Öneri: child keşfi başarısız olsa da doğrulanmış Popen üzerinde cleanup'ı sürdür.
Başarı kanıtı yoksa sessizce tamamlanmış sayma. AccessDenied/NoSuchProcess,
surviving process ve timeout için ayrı test ekle.

### A-03 — P2: Süreç API'si doğrulanmamış ham PID kabul edecek şekilde genişlemiş

Konum: PR #4 `core/process_tree.py:10`, `:26–30`, `:43–61`.

Yeni fonksiyon ham integer PID kabul edip bu numaradan bulduğu process'e
terminate gönderiyor. Bu yolun sahip olunan Popen veya önceki start-time/exe
kimliğiyle bağı yok. Mock ölçümünde yalnız integer verilerek terminate çağrısı
üretildi. Bu, gerçek sistemde yanlış süreç öldürüldüğünün canlı kanıtı değildir;
yeni API'nin sahiplik doğrulamadığının kaynak/fixture kanıtıdır.

Öneri: sahipliği kanıtlı Popen sözleşmesini koru veya gerekli kimlik kaydıyla
çalış. Gerçekten yeniden atanmış bir Windows PID senaryosu canlı denenmedi.
Raporun “zero orphan” garantisi de koddan çıkarılamıyor: kök PID yoksa kod
descendant envanteri bulmadan dönüyor; kopmuş eski çocukları takip eden kayıt yok.

### A-04 — P2: Boyut sınırı genç logların korunması sözleşmesini değiştiriyor

Konum: PR #4 `core/low_spec_optimizer.py:424`.

Silme koşulu `old OR over_size`; dolayısıyla yaş eşiğini karşılamayan dosya
da silinebiliyor. Aktif CLI kontrolü log dalını engellemiyor; yalnız lock/backup
dallarına uygulanıyor. En yeni N dosyayı korumak, daha eski sıradaki dosyanın
aktif yazılmadığını kanıtlamaz.

Yalnız üretilmiş TemporaryDirectory dosyalarıyla ölçüm: üç adet 600 KiB log,
en yaşlısı iki dakika, max_age48h/keep1/cap1MiB; iki genç dosya silindi.
Kullanıcının gerçek logları bu deneyde kullanılmadı.

Öneri: yaş korumasını ve aktif dosya korumasını sürdür; boyut sınırını bu
kuralları sağlayan adaylara uygula. Son N dosya tek başına sınırı aşarsa bunu
metadata'da bildir. Bu koşulda “hard cap enforced” sonucu verilemez.

### A-05 — P2: Performans oranları karşılaştırılabilir deneylerden gelmiyor

Konum: `scripts/measure_runtime_efficiency_baseline.py:92–112` ile
`scripts/measure_runtime_efficiency_comparison.py:71–91` ve performans raporu.

Baseline ölçümü her read'den sonra `sleep(0.002)` yapıyor ve bunu elapsed
süresine dahil ediyor. Sonraki ölçümde bu bekleme yok. Read sayısı, key dizisi,
loader verisi ve TTL de farklı. Bu nedenle 3022µs → 7.68µs ve “>%99” ifadesi
aynı iş yükünün hızlandığını kanıtlamıyor. Yeni `read()` de her çağrıda deepcopy
yapıyor; ek cache ilk refresh'te ikinci bir kopya tutuyor.

RAM ölçümü çalışan paketli Quartz yerine test Python sürecinde 30 MiB buffer
ayırıp serbest bıraktıktan sonra working set'i kırpıyor. Bu, Windows çağrısının
çalışabildiğine kanıttır; Quartz'ın kalıcı belleğinin %96.2 azaldığını kanıtlamaz.
Thread9→8 ve lookup hızları da gerçek uygulamanın eşleştirilmiş A/B ölçümü değil.

Öneri: aynı harness, aynı veri/süre ve ısınma koşullarıyla baseline ve aday
çalıştırılsın. RSS yanında private bytes/USS ve task sonrası tepki süresi
gösterilsin. Gerçek uygulama performansı UNKNOWN olarak ayrı tutulsun.

### A-06 — P2: Yeni idle/chat/active profilleri uygulama döngüsüne bağlı değil

Konum: PR #4 `core/low_spec_optimizer.py:81–106`, `:141–145`.

Profil sözlüğü üretiliyor fakat üretim çağrı zincirinde state seçip bunu kullanan
kod bulunmadı. GUI hâlâ mevcut sabit süreleri ve `lowSpecHardware`/idle koşullarını
kullanıyor; yeni `profiles` sözlüğünü okumuyor. Sahiplik
sınırına uyulduğu için GUI değiştirilmemesi doğru; eksik bağlantının integration
request olarak raporlanması gerekiyor. Mevcut PR için “aktif uyarlamalı polling”
kabulü verilemez.

## Claude teslimi

Sahiplik uygun: yalnız `gui.py`, `ui/`, yeni frontend testleri ve kendi mimari
belgesi değişmiş. Yeni bağımlılık veya arka uç API değişimi yok.

Bağımsız Windows karşılaştırması: baseline'ın gerçek `_HTML` literal'i AST ile
okunup aynı CSS/marka enjeksiyonu uygulandı; yeni production builder çıktısıyla
tam eşit:

- Önce/sonra karakter sayısı: 193008 / 193008.
- İkisinin SHA-256 değeri:
  `9cf9fc6d017a98c44cd6c4c2e51e994be5566daf3f8352cd9abd312c1308c01d`.
- 53 hedefli Windows testi PASS, gömülü JavaScript exit0.
- Tam yerel Windows koşusu: 674 case, 662 PASS, 12 SKIPPED.
- Windows GitHub CI PASS.

Bu ilk güvenli ayrıştırma dilimidir. HTML gövdesi, JS ve Python Api köprüsü
hâlâ gui.py içinde; tüm frontend ayrıştırması bitmiş değil. Claude raporu bunu
açıkça belirtiyor. Tam Windows Quartz.spec paketi ve gerçek görsel kabul henüz
yapılmadı. Import analizinin ui modüllerini bulması makul; bu inceleme bunu tam
paket oluşturulmuş gibi sunmuyor.

## Codex teslimi

PR #2'nin yalnız Codex-owned kaynak/test/rapor dosyaları değişmiş. GitHub
Windows CI 677 case, 665 PASS, 12 SKIPPED. Önceki bağımsız iç inceleme sekiz
yeni özgün testi doğruladı. Aynı sınıfın başka test modülünde import edilmesi
test sayısını artırıyor; 677 bağımsız özellik/senaryo iddiası yok.

Bu incelemede PR #3/#4 ile geçici birleştirme çatışmasız gerçekleştirildi.
Bu, main'e merge veya kurulu uygulamaya dağıtım değildir.

## Test ve izolasyon

- Bütün dış PR'lar aynı koordinasyon baseline'ından ayrılmış. Sahiplik listeleri
  arasında değiştirilen dosya çakışması yok.
- PR #4 için 32 hedefli Windows testi PASS. Yeni kontrollü hata probe'ları
  A-01/A-02 sorunlarını ayrıca gösterdi; mevcut testlerin yeşil olması bu
  davranışları kapsadıkları anlamına gelmiyor.
- PR #4'ün 64-bit ctypes imzaları ve süreç ağacı thread telemetrisi yararlı
  değişiklikler. Kendi Python test sürecinde OS working-set çağrısının başarılı
  olmasını bekleyen test PASS; bu, paketli uygulama bellek kazancı değildir.
- Üç PR geçici detached worktree'de `--no-commit` ile birleştirildi. Üretim
  branch'leri ve ajan worktree'leri değiştirilmedi.
- Birleşik Python sözdizimi: 215 dosya PASS. Gömülü JS exit0. Staged yayın ve
  geçmiş denetimi PASS/bulgu0; whitespace kontrolü PASS.
- Birleşik tam regresyon: **701 case, 689 PASS, 12 SKIPPED**, 73.505 saniye.
  Varsayılan suite test sınıfı importlarından kaynaklanan tekrarları içerir;
  701 bağımsız işlev veya canlı senaryo anlamına gelmez. Yeni hata probe'ları
  bu suite'e eklenmediğinden suite'in yeşili A-01/A-02'yi geçersiz kılmaz.

Kanıt probe dosyaları:

- `C:\Users\LENAVO\.codex\backups\quartz-delivery-review-20261031\review_probes.py`
- `C:\Users\LENAVO\.codex\backups\quartz-delivery-review-20261031\frontend_equivalence.py`

İnceleme worktree'leri:

- Claude: `C:\Users\LENAVO\.codex\worktrees\quartz-review-claude-20261031`
- Geçici birleşim: `C:\Users\LENAVO\.codex\worktrees\quartz-review-combined-20261031`

Probe'lar gerçek uygulama başlatmaz ve gerçek kullanıcı loglarını silmez.
Süreç sonlandırma hata deneyleri mock; normal süreç testleri yalnız kendi
oluşturdukları fixture süreçlerini kullanır. Snapshot deneyi gerçek Python
thread'leri ve Event nesneleri kullanır.

## Önerilen sonraki adım

1. Claude'un ilk dilimini kaynak açısından kabul edilebilir tut.
2. Antigravity'ye A-01/A-02'yi düzeltme, A-03/A-04 sözleşmesini koruma ve
   A-05/A-06 iddialarını düzeltme görevi ver. İlgili dosyalar onun sahipliğinde.
3. Yeni commit'te mevcut testlere ek bu hata probe'larının regresyonları çalışsın.
4. Yeniden incelemeden sonra üç aday tek staging paketinde gerçek Windows
   kabulüne girsin. Ana sohbet/onay/Stop, tema/Q işareti, süreç cleanup ve gerçek
   kaynak tüketimi gözlensin.
5. Kimi'nin bağımsız kalite/temiz kurulum denetimi tamamlanmış sayılmasın;
   erişim yeniden sağlandığında veya yerel inceleme olarak ayrıca yürütülsün.

Bu incelemede source düzeltmesi, PR yorumu, merge, push veya kurulu EXE
güncellemesi yapılmadı. ASTER rafa kaldırılmış durumda; dış proje dosyalarına
ve korunan verilere dokunulmadı.
