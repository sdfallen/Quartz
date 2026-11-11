# Codex mimari kapanış dilimi — 2026-11-02

Ortak başlangıç `2c57a49`; Codex'in önceki tamamlanmamış checkpoint'i `d55b32f` bu dilimde tamamlandı. Bu rapor yalnız Codex sahipliğidir. Claude ve Antigravity teslimlerinin birleştiği veya yeni Quartz.exe'nin canlı kabul edildiği anlamına gelmez.

## Tamamlanan sınırlar

- Mevcut chat turn kimliği task korelasyonu olarak korunur; provider run/session ve Squad kimlikleriyle karıştırılmaz.
- Aktif göreve aynı sohbet/ajan ve donmuş yetki kapsamında ek talimat sıraya alınır. Ayrı çalışan açılmaz; mevcut adım ve dosya denetimi bitmeden ikinci yazıcı başlatılmaz. İptal/başarısızlık bekleyen talimatları çalıştırmaz. Kesilen kuyruklar restart sırasında otomatik tekrarlanmaz.
- Stop önce yerel yayını engeller. Provider exit, çalışan sonlanması ve writer/journal sahipliği ayrıca okunur. Yerel cancelled ile gerçek cleanup confirmed ayrıdır. Geç dispatch sonucu da gerçek run ID ile iptal edilir.
- Kayıt I/O hatası süreç iptalini atlatamaz; güvenli error-type alanı ve yeniden denenebilir failed receipt döner. Kısmi grup başarısı, diğer provider'ın açık kalan sürecini gizlemez.
- Runtime başladıktan sonra dispatch/journal hatasında bilinen run ID kaybolmaz. Bilinmeyen başlangıç ownership'i pending kalır; boş run listesi temiz kapanış kanıtı sayılmaz. Belirsiz writer claim silinmez veya otomatik tekrar yürütülmez.
- ConversationStore okumaları ve mesaj metadata'sı ayrık kopyadır; yalnız görüntüleme için eklenen host evidence gerçek geçmişe sızmaz.
- Frozen package doğrulayıcısına frontend'in sekiz yeni UI modülü eklendi; bu, henüz yeni paket üretilmiş demek değildir.

## Somut kusur kanıtları ve regresyonlar

Başarısız yeniden üretim: shared nested read model nedeniyle yetkisiz in-memory geçmiş/model değişimi; 3 testte 5 assertion failure. Düzeltmeden sonra ilgili testler geçti. Ayrı read-only inceleme; failed worker'ın finalization aralığında yeni görevin eski sahipliği silmesini, Stop history yazma hatasının provider cancellation'ı atlatmasını ve interrupted followup'ın geçmişe sızmasını disposable fixture ile doğruladı. Geç dispatch, kısmi grup başarısı, writer-release/dequeue yarışı ve dispatch sonrası journal failure için regresyonlar eklendi.

Eski bir test start metodundan gelen her OSError sonrasında kilidin bırakılmasını bekliyordu. Bu beklenti, mevcut durable-uncertainty sözleşmesiyle çelişiyordu: start çağrısının hata vermesi süreç hiç oluşmadığının kanıtı değildir. Test, belirsiz başlangıçta recovery-required exclusion ve otomatik retry olmamasını doğrulayacak şekilde düzeltildi. Start öncesi başarısız checkpoint'in kilidi bırakması ayrı testlerde korunur.

## Doğrulama

| Düzey | Sonuç | Kapsam |
|---|---|---|
| SOURCE / hedefli | PASS — 116 case | Lifecycle, gerçek geçici store, izin/kimlik/recovery, kontrollü fake provider'lar |
| SOURCE / tam Windows suite | PASS — 898 case, skip yok | `scripts/run_safe_tests.py`; 96.191 saniye; test case sayısı bağımsız ürün senaryosu sayısı değildir |
| JavaScript | PASS — Node exit0 | Gerçek statik UI composition; frontend davranışı bu Codex diliminde değiştirilmedi |
| Yardımcı EXE | BUILT | Mevcut DesktopMCP helper yerel test için kaynak üzerinden derlendi; guard kaldırılmadı |
| Gerçek Codex kaynak sohbeti | LIVE VERIFIED | Kaydedilmiş mevcut `gpt-6-sol` tercihi; aynı task'ta iki sıralı mesaj; gerçek `43` / `17`; iki run exit0 ve process_exit_confirmed |
| Gerçek Antigravity kaynak sohbeti | LIVE VERIFIED | Mevcut `gemini-3.8-flash-medium`; aynı task'ta iki sıralı mesaj; gerçek `43` / `17`; iki run exit0 ve process_exit_confirmed |
| Gerçek Stop | LIVE VERIFIED | Canlı Codex run ID gözlendi, normal cancel uygulandı, receipt confirmed ve gerçek çıkış doğrulandı |
| Paketli ana sohbet / masaüstü | NOT TESTED — birleşim bekliyor | Claude GUI/servis ve Antigravity backend/entry teslimleri bu dalda henüz yok |
| Yeni üretim Quartz.exe | NOT BUILT / NOT DEPLOYED | Kurulu kabul edilmiş paket korunuyor |

Canlı test izole disposable proje/store ile ve mevcut hesap CLI oturumları üzerinden çalıştı. API key'e geçilmedi, kullanıcı modeli değiştirilmedi, gerçek projeye yazma veya masaüstü girdisi yapılmadı. Bu test yazma görevi/gerçek GUI onayı kabulü değildir. Codex yanıtları toplam 14.239, Antigravity 22.272 saniyede tamamlandı; eşleştirilmiş performans karşılaştırması veya hız kazancı iddiası yok. Codex run'larında 3/4, Antigravity run'larında 1/1 tanı satırı sayıldı; tamamen temiz CLI çıktısı iddia edilmiyor.

İlk Antigravity denemesi worktree'deki observer güvenlik yardımcısı eksik olduğu için provider başlamadan FAILED oldu ve ek talimat doğru iptal edildi. Güvenlik kapatılmadan mevcut helper derlendi; sonraki gerçek deneme geçti. İlk başarısızlık kanıtı korunur.

İki önceki hedefli koşuda eski 500 ms durum-okuma zaman testi 0.783/0.554 saniye ölçüp başarısız oldu; tekil tekrar ve son hedefli/tam suite geçti. Eşik gevşetilmedi. Bu gözlem kalıcı performans sorununun çözüldüğü iddiası değildir.

## Kanıt ve devam

Yerel özel kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-codex-lifecycle-20261102`.

- `read-model-before.log`: düzeltme öncesi somut başarısızlık.
- `targeted-complete-final.log`: son 116 hedefli case.
- `safe-suite-reviewed-final.log`: son 898 case, helper hazır olduğundan skip yok.
- `live-source-chat.json` ve `live_source_chat.py`: son gerçek kaynak sohbet/Stop ölçümü ve çalıştırılan sürücü; kaynak SHA-256 değerleri içerir.
- `live-source-chat-attempt1.json`: helper önkoşulu eksik ilk koşu.
- `helper-build.log`: yalnız test yardımcısının gerçek derlemesi.

Canlı koşu sonunda her iki provider instance'ında owned process count 0, text workspace count 0 ve chat cleanup confirmed gözlendi. Başka uygulamaların süreçleri kapatılmadı.

Claude/Antigravity için kesin payload ve cleanup beklentileri `CODEX_LIFECYCLE_CONTRACT.md` içinde. Özellikle GUI'deki mevcut `if (thinking) return` koşulu, backend kuyruğuna ulaşmayı engelleyebilir; Claude'un sahip olduğu arayüzde bu bağlantı ve pending/failed receipt görünümü ayrıca tamamlanmalıdır.

Belirsiz post-start hatası doğal başarı gibi sunulmaz. Durable exclusion yerinde kalır; mevcut restart ve açık external recovery review akışı gerekir. Servis/entry kapanışının bu pending receipt'i ele alması Antigravity birleşim kapısıdır. Otomatik izin, claim silme, re-dispatch veya ikinci görev motoru eklenmedi.

Codex dilimi SOURCE ve sınırlı gerçek CLI kanıtıyla entegrasyona hazırdır. Bütün mimari IN PROGRESS: iki dış teslimin incelenmesi, birlikte tam regresyon, yeni Windows paket doğrulaması ve ana sohbet → görev → ek talimat → Stop → yeniden açılış canlı kabulü kaldı. ASTER ve Notion üçüncü ajan kapsam dışıdır. Bu kaynak commit'leri geri alınarak ortak temiz başlangıca dönülebilir; kullanıcı verisi geri alma işlemi gerekmez.
