# Görev Sınavı koşucusu

Bu araç yeni bir görev motoru değildir. İncelenmiş kabul adaptörlerini sırayla
çalıştırır ve özel kanıt dizinine sonuç yazar. Claude'un yaklaşık 30 gerçek
görevini henüz içermez; örnek liste altyapı smoke kontrolüdür, G1–G8 skoru değildir.

```powershell
python -B scripts/task_exam_runner.py --manifest docs/task_exam_manifest.example.json --output C:\PrivateEvidence\exam-new
python -B scripts/task_exam_runner.py --manifest docs/task_exam_manifest.example.json --output C:\PrivateEvidence\exam-run --execute --package C:\Path\Quartz
```

İlk komut dry-run yapar. Kanıt yolu yeni olmalı ve herhangi bir Git checkout'u
altında bulunmamalı. `--package` yalnız EXE hash/boyutunu okur, uygulama açmaz.
Ham stdout/stderr özel dizinde kalır. Repo'ya screenshot, konuşma, hesap bilgisi
veya gerçek çalışma sonucu otomatik kopyalanmaz.

Her satırda source SHA, kirli kaynak uyarısı, paket özeti, süre, sonuç ve adım
sayısı alanı bulunur. Agent adımları ölçülmüyorsa `step_count=null`; süreç açma
sayısı agent adımı diye sunulmaz. Gelecekteki incelenmiş adaptörler
`QUARTZ_TASK_EXAM_DIR/steps.json` içine `{"step_count": 3}` yazabilir. Bu ölçüm
tek başına görev başarısını doğrulamaz. Görev başına bağımsız oracle gerekir.

Yalnız iki adaptör etkin:

- `regression`: repo'daki `tests.test_*` modüllerini mevcut safe-suite üzerinden
  çalıştırır. Gerçek test/skip adedini unittest çıktısından okur; LIVE değildir.
- Sentetik süreç ölçümü: katalog SHA'sı eşleşmeli ve gerçek
  `stop_cancellation.stop_verified` true olmalıdır. Exit0 tek başına yeterli değil.

Diğer scriptler katalogda sınıflandırılmıştır ama özel output/cleanup adaptörleri
incelenene kadar çalışmaz. Hesap/masaüstü bayrakları onay kanıtı değildir;
operatör yalnız güncel kullanıcı izni ve masaüstü slotuyla bunları kullanabilir.
Bu teslimde bu bayraklarla hiçbir gerçek çağrı yapılmadı. Legacy oyun/Notion
testleri kapalıdır. Manifest shell komutu, ortam değişkeni veya keyfî executable
taşıyamaz. Kaynak script değişirse hash kapısı yeniden inceleme ister.

Sonuçlar SOURCE ve TESTED seviyesindedir. Exit0, modelin "tamamlandı" sözü,
test-suite başarısı veya paket hash'i USER ACCEPTED/LIVE VERIFIED üretemez.
Ctrl+C'de yalnız oluşturulan Popen ağacı durdurulur; sonraki görev başlatılmaz.
Cleanup kanıtlanmazsa BLOCKED kalır. Test timeout'u ürün görev süresi değildir.

CLI çıkışı: tüm görevler oracle ile VERIFIED ise 0; dry-run, boş liste,
engellenen veya başarısız görev varsa 2. Ham loglar yalnız özel dizindedir.

Bkz. `TASK_EXAM_SCRIPT_INVENTORY_20261105.md` ve
`scripts/task_exam_catalog.json`. Canlı görev tasarımı Claude'da, bu dilimde
koşucu ve sınıflandırma kullanıcının güncel talimatıyla Codex'tedir.
