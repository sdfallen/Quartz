# Görev Sınavı: host kontrolleri ve plan aracı (7 Kasım 2026)

Dal: `claude/night-fixes-20261107`. Seviye: SOURCE + TESTED. Hiçbir sınav görevi gerçek hesapla koşulmadı.

## Eklenenler

| Dosya | Ne yapar |
|---|---|
| `scripts/exam_oracle.py` | Görev listesindeki başarı koşullarını yalnız host verisiyle değerlendirir: fixture klasörü, koşu öncesi host anlık görüntüsü (`snapshot`), host'un yazdığı fixture durum dosyası ve Quartz'ın koşu kaydı. `human_grade` ve yazılmamış her kontrol görevi asla `VERIFIED` yapmaz. Bir host kontrolü başarısızsa sonuç `FAILED`. Yollar fixture dışına çıkamaz; `python_compiles` fixture'a `.pyc` yazmaz. |
| `scripts/exam_plan.py` | `docs/task_exam/tasks_20261105.json` listesini doğrular, her koşu için `<nonce>`/`<nonceN>` yerine host'un ürettiği rastgele değerleri koyar, çevrimdışı görevleri `scripts/task_exam_runner.py` manifestine çevirir ve kapsam raporu verir. Hiçbir şey başlatmaz. |
| `tests/test_exam_oracle.py` | 11 test: BOM/CRLF normalleştirme, baseline karşılaştırması, fixture dışına çıkış, derleme kontrolünün fixture'ı değiştirmemesi, insan/eksik kontrolün doğrulamaması, koşu kaydı alanları, durum dosyası sınırı, liste doğrulama, nonce tazeliği, kapsam sayımı. |

## Kapsam (kod çalıştırılarak ölçüldü)

`python -B scripts/exam_plan.py`: 35 görev, liste geçerli.

- Tam otomatik kontrol edilebilen: 4 (`exam-desk-02`, `exam-long-03`, `exam-code-08`, `exam-prov-01`).
- İnsan değerlendirmesi isteyen: 7.
- Henüz yazılmamış kontrol adı: 63. Çoğu canlı kanıt ister: masaüstü giriş olayları, izin kartı zamanlaması,
  süreç ağacı, Stop makbuzu, CPU/süreç sayımı, öğrenme kayıtları.

## Sonraki adım

Canlı kanıt katmanı: sınav profilinde Quartz'ın broker denetim kaydı, `result.json`, fixture olay dosyası ve
süreç örneklemesinden `Context.events` / `outcome` / süreç alanlarını dolduran adaptör. Bu kısım gerçek hesap,
masaüstü slotu ve kullanıcı onayı ister; önce `adapter_order` sırasındaki üç görev (`exam-code-01`, `exam-chat-01`,
`exam-desk-02`).
