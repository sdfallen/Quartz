# Otomatik düzeltme döngüsü ve çok dosyalı fikstür — başlangıç teslimi

Taban a182779; dal codex/repair-loop-20261109. Bu çekirdek mevcut AgentChat'e henüz bağlanmadı. Üretim sohbetinin otomatik repair yaptığı iddia edilmiyor. Yeni task registry/runtime veya model aracı kurulmadı.

## Uygulanan politika

core/repair_cycle.py: host test gözlemi başarısızsa en fazla max_repairs kez aynı writer_id callback'ine son 16000 karakter test çıktısı gönderilir. Her yazmadan önce complete+archive/ref checkpoint gerekir. Test sayısı0, eksik exit code ve altyapı hatası blocked; başarılı test tests_passed üretir, bütün hedefi veya kullanıcı kabulünü VERIFIED yapmaz. Tek kullanımlı cycle, thread-safe replay koruması ve aşamalar arası Stop kontrolü vardır. Callback'ler çalışan süreçleri mevcut sahiplik/cancel sistemiyle kesmek zorundadır; Python callback zorla sonlandırılmaz.

tests/test_repair_cycle.py: 7 test PASS (başarısız→onar→başarılı, aynı yazıcı, checkpoint ret, zero-test ret, limit, Stop, replay). Gerçek model çağrısı yok.

## Fikstür

docs/task_exam/fixtures/invoice: 8 dosya; 5 uygulama modülüne yayılan fiyat/vergi/servis/biçimlendirme/render işi. Host testleri değişmez kalmalı. Geçici kopyada gerçek unittest komutu başlangıçta 8 vaka koştu, exit1, errors15 (subtest hataları dahil). Bu beklenen başarısız başlangıçtır, çözüm veya canlı kabul değildir. Test/model dosyalarını hash ile koruyacak host hazırlığı sonraki adaptörde bağlanmalı. Yeni dependency/ağ/hesap gerektirmez.

## Sonraki AgentChat bağlantısı — IR-REPAIR-CHAT-01

1. Host tarafından önceden seçilmiş proje/test planı gerekir; sohbet/model metni keyfi test komutu veya başarı eşiği kaydedemez.
2. _execute_codex_bubble / _execute_antigravity_bubble sonrası mevcut writer watcher/journal cleanup doğrulanmadan ikinci dispatch yapılmaz. Aynı provider, model, proje ve yetki korunur; retry yeni run_id alır, asıl task/conversation bağı sürer.
3. Callback'ler mevcut _dispatch_chat_run, runtime.cancel ve Stop event'ini kullanmalı. Pause/UAC/scope değişiminde tekrar yazım başlamamalı. Checkpoint her repair'den önce create_checkpoint ile alınmalı.
4. Host unittest parser'ı stdout'taki model metnini başarı saymamalı; gerçek process exit ve güvenilir test sayısı kullanılmalı. Timeout/cleanup belirsizliği blocked olmalı.
5. Attempt/checkpoint/run receipt'i RunEvidenceStore'a bağlanmalı; ham hata çıktısı kullanıcı verisi içerebileceğinden yalnız yerel kapsamda tutulmalı. Goal oracle ve UI yeni attempts alanını ayrı gösterebilir; tests_passed USER ACCEPTED değildir.
6. Claude bağımsız incelemesi ve paketli canlı seeded görev bu temelden sonra gerekli. Bu dal bağımsız incelemeden main'e alınmadı.

## Doğrulama ve sınır

Üç merge/S3 için 38 hedefli test geçti; bu yeni bileşen için 7 test geçti. Python syntax351 dosya, JS exit0 ve diff check temiz. Tam suite yeni başlangıç bileşeni için yeniden koşulmadı; paket derlenmedi/kurulmadı, gerçek ajan/masaüstü açılmadı. S3 ve üç merge inceleme belgesi main'dedir; yeni repair kodu ayrı daldadır. cb962b7 P1 critical-control bulgusu açık kalır (CODEX_THREE_MERGE_REVIEW_20261109.md).
