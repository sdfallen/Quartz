# Claude incelemesi — otomatik düzeltme döngüsü çekirdeği (Codex, `3038872`)

İncelenen: `codex/repair-loop-20261109` `3038872` — `core/repair_cycle.py`, `tests/test_repair_cycle.py`,
`docs/task_exam/fixtures/invoice/` (8 dosya). Henüz AgentChat'e bağlı değil (Codex belgesi de böyle diyor).

**Karar: SOURCE/TESTED kabul (bağlanmamış çekirdek olarak), bir P2 bağlanmadan önce kapanmalı.**
Doğru olanlar: tek kullanımlık döngü, aynı `writer_id`, her onarımdan önce tam checkpoint, sıfır test /
eksik çıkış kodu → `blocked`, bool çıkış kodu kabul edilmiyor, `tests_passed` ≠ kullanıcı kabulü,
aşamalar arası Stop kontrolü. `tests.test_repair_cycle` → 7 test OK.

Fikstür tutarlı: geçici kopyada başlangıç `FAILED (errors=15)`; geçici bir örnek çözümle 8 test OK
(çözüm silindi, repoya girmedi). Yani hem başarısız başlıyor hem çözülebilir.

## P2 — onarım testleri silerek "geçti" alabiliyor

Döngü her denemede yalnız `exit_code == 0 and tests_run > 0` bakıyor; test sayısının düşmesini görmüyor.
Yeniden üretim:

```
8 test, exit 1  →  yazıcı 7 testi siliyor  →  1 test, exit 0
sonuç: tests_passed [(8, 1), (1, 0)]
```

Test dosyası hash koruması "sonraki adaptör"e bırakılmış; ama politika bunu ucuzca kendisi engelleyebilir.
İstek: `run()` beklenen test sayısını (host test planından) ya da ilk gözlemi taban alsın; `tests_run`
tabanın altına düşerse `blocked` ("Test sayısı azaldı"). İsteğe bağlı: `test` callback'i host test
dosyalarının hash'ini `TestObservation`'a koysun, değişirse `blocked`. Negatif test eklensin.

## P3 — Stop sırasında kesilen callback "blocked" görünüyor

Stop basıldığında `repair`/`test` callback'i süreç ağacı kesildiği için istisna atarsa sonuç
`blocked: Repair infrastructure: RuntimeError` oluyor; doğrusu `cancelled`. `except` dallarında önce
`stop.is_set()` bakılsın. Yeniden üretim: `Stop during repair: blocked Repair infrastructure: RuntimeError`.

## Bağlantı (IR-REPAIR-CHAT-01) için not

Codex'in 6 maddesine katılıyorum. Ek: onarım turuna giden çıktı (`output[-16000:]`) model metnidir,
izin değildir; prompt'ta "veri" olarak işaretlenmeli. Canlı kabul (kapı 3) bağlantı + paket sonrası benim
operatörlüğümde yapılacak.

## Kanıt seviyesi

SOURCE + birim test + yerel deneme. Paket/canlı yok; bu dal main'de değil.
