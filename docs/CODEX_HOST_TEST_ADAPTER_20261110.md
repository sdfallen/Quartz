# Gerçek host unittest runner/adaptörü — 10 Kasım 2026

Dal: codex/repair-loop-20261109. Üretim kodu: 31c2309d73caa114ddc0956754ea6c4f3484ff23 + 51e0ed1a26aca7c07e61a1fd6c84e826294147f5.
Önceki manifest zorunluluğu ve içerik koruma düzeltmesi c2cbadb korunur.

## Başlangıç hash'i ve bağlama

AgentChatService.register_host_unittest_plan(...), yalnız host Python API'sidir.
IPC/MCP/UI/model için yeni uç yoktur. Yalnız açıkça seçilen kayıtlı proje ve tek
yazıcı için çağrılır; aktif yazıcı varken baseline alınması reddedilir.
Korunan/Warband workflow reddedilir. Test dosyaları bu çağrıda, HİÇBİR ajan veya
test süreci başlatılmadan okunur. Göreli dosya adları sıralanır; manifest immutable
tuple((dosya_adı, sha256), ...) biçimindedir. Dizin kaçışı, link/reparse ve dosya
boyut sınırları kontrol edilir. Host planı pozitif expected_tests ister.

send_message ilk dispatch'ten önce validate_baseline çağırır. Test dosyası
kayıttan sonra değiştiyse ilk yazıcı hiç başlamaz. Callback her testten önce ve
sonra aynı ilk baseline'ı kontrol eder; yeni hash'i taban olarak benimsemez.

Örnek host hazırlığı (proje/kullanıcı izni önceden mevcut olmalı):

```python
adapter = chat.register_host_unittest_plan(
    conversation_id, project_id=project_id, provider='codex',
    test_files=('test_invoice.py',), expected_tests=8,
    python_executable=approved_python_path, timeout=30,
)
# Bu noktada manifest hazırdır; model/test henüz çalışmamıştır.
chat.send_message(task, agent='codex', conversation_id=conversation_id,
                  write=True, confirm_write=True)
```

Host uygulaması bu API'yi çağırmalıdır; normal sohbetten otomatik test planı
çıkaran veya keyfi shell komutu kabul eden bir yol eklenmedi. Paketli uygulamada
Python açıkça seçilmelidir (frozen Quartz.exe Python yorumlayıcısı sayılmaz).

## Gerçek test süreci

core/host_test_runner.py standart unittest'i host'a ait sabit child koduyla,
onaylı Python'da -I/-B seçenekleriyle çalıştırır. Proje root'u ve test modülleri
host planından gelir; shell kullanılmaz. Stdout/stderr başarı parser'ı değildir.
Unittest result.testsRun/skipped ve gerçek process exit, ayrı JSON receipt ile
eşleştirilir. Eksik/uyuşmayan receipt, eksik test, skip, timeout veya fazla çıktı
blocked olur. Başarısız gerçek test exit1 gözlemi repair'e iletilir. Ortam yalnız
PATH/Windows/TEMP alanlarından oluşur; API anahtarı veya .env yüklenmez.

Çocuk test kodu çalıştırılması, yetkilendirilmiş proje kodunun yürütülmesidir;
kötücül kod için OS güvenlik sandbox'ı olduğu iddia edilmez.

Windows'ta Popen CREATE_SUSPENDED başlar; mevcut process_tree Job Object bağlama
işleviyle sahiplik kurulmadan test kabul edilmez. Stop, timeout ve normal çıkışta
yalnız bu owned job sonlandırılır, aktif süreç sayısı0 ve root exit okunur; sonra
handle bırakılır. Normal çıkışta geride kalan child da temizlenir. Son receipt ve dosya hash okumaları ancak bütün owned süreçlerin kapanışı doğrulandıktan sonra yapılır; dosya/receipt okumaları boyut sınırlarıyla tutulur. Temizlik
doğrulanamazsa adapter referansı korunur, yeni görev admission ve confirmed Stop
makbuzu engellenir. Model/desktop/sistem ayarı değiştirilmez.

Gerçek process runner Windows Job Object gerektirir; diğer platformlarda fail-closed.
Taşınabilir manifest testleri çalışabilir; Windows process testleri diğer OS'de
açıkça skip olur. Bu oturum Windows'tadır; yeni process testleri atlanmadı.

## Gerçek doğrulama

Hedefli komut: scripts/run_safe_tests.py tests.test_host_test_runner
tests.test_repair_cycle tests.test_chat_repair tests.test_agent_chat tests.test_multi_agent_service
→ Nihai 51e0ed1 hedefli koşusu: Ran53 tests in7.604s / OK, skip0, exit0.

Ölçülen senaryolar: gerçek unittest pass ve fail; stdout'ta sahte OK metni;
skip/timeout ret; gerçek Stop ve child process sonlandırma; normal exit sonrası
child temizliği; sıralı tuple; pre-dispatch hash değişimi ve hiç dispatch olmaması;
cleanup belirsizken admission/Stop confirmation engeli; geçici invoice fikstüründe
gerçek8 test exit1 (başlangıçtaki kasıtlı eksikler, başarılı onarım iddiası değil).

Son kaynakta Python syntax359 dosya OK; JS exit0; yayın denetimi PASS (600 dosya / 1287 geçmiş blob / bulgu0); diff check temiz.
Nihai üretim SHA 51e0ed1 üzerinde tam takım: Ran1646 tests in215.699s / OK (skipped=2). İlgili Python test süreci normal tamamlandı. Önceki 31c2309 tam takım koşusu da1646 test / OK (skipped=2),250.699s; nihai sürümün yerine sayılmıyor.

## Ortam ve dürüstlük sınırı

PATH'teki Python3.13.17 ilk denemede dotenv bulamadı; test başlamadı. Eski Store
yorumlayıcısını doğrudan başlatma PowerShell StandardOutputEncoding hatası verdi.
Sistem kurulumu/PATH değiştirilmedi. Var olan Store site-packages dizini yalnız
bu test process'inde site.addsitedir ile yüklenerek Python3.13.17 kullanıldı.
Yalnız PYTHONPATH ile ilk tam deneme1646 test/3 error/2 skip verdi; üç hata
pywintypes yüklenmemesiydi. site.addsitedir ile aynı3 test tekrarında3/3 geçti.
İlk başarısız log korundu. Bunlar adapter kodu hatası olarak sunulmuyor.

Ham loglar repo dışında .codex/backups/quartz-review-20261109/ altında
host-runner-targeted-final.log, host-runner-full.log,
host-runner-environment-recheck.log, host-runner-full-confirmed.log, host-runner-hardened-targeted.log ve host-runner-final-frozen.log ve host-runner-final-targeted.log.

Yeni paket derleme/kurulum, push veya gerçek model/GUI oturumu yapılmadı.
Kalan: bağımsız Claude incelemesi; onaylı paket üzerinde uygun host başlangıç
yolunun operatör hazırlığı; doğal model onarımı ve Stop içeren canlı kapı3.
Kaynak ve yerel süreç testleri LIVE model/USER ACCEPTED sayılmaz.
