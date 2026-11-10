# Host adaptörü — Claude P1/P2 incelemesi sonrası düzeltme

Dal: codex/repair-loop-20261109
Üretim commit: e50f265c8006e8b8b6e3ea12f5ab86775c0547d3 +4fd3b44cc9802df96a2b10bf7f11866b39ac8dd9
Önceki reddedilen kaynak:31c2309 +51e0ed1; rapor b9ddd9b.
İnceleme girdisi: repo dışı to-codex/20261110-2120-claude-review-51e0ed1.md.

## P1: önce gerçek yeniden üretim

Claude'un invoice.py → sys.argv[3] yoluna JSON yazma → os._exit(0) örneği,
test dosyası hash'i aynıyken passed=True üretti. Regresyon testi düzeltmeden önce
12 testte1 failure verdi (test_production_module_cannot_forge_argv_receipt).
Bu gerçek kusurdur; önceki test takımının yeşil olması bu açığı kapsamıyordu.

## P1: uygulanan dar düzeltme

- core/host_test_runner.py:26-37,163-179: makbuz yolu argv'den çıkarıldı.
  Host her koşuda32 rastgele bayttan nonce üretir; nonce ve makbuz yolu yalnız
  owned child stdin pipe'ından gönderilir. Worker proje importundan önce okur,
  stdin'i kapatır, sys.argv'yi temizler. Kontrol verileri loglanmaz.
- Aynı dosya201-214: missing/wrong nonce blocked. Gerçek process exit ve receipt
  kontrolüne ek olarak TextTestRunner'ın en son Ran N tests satırı da receipt
  tests_run ile aynı olmalı. Stdout tek başına karar vermez.
- Normal exit/Stop/timeout sonrası Job Object temizliği ve cleanup kapıları korunur.
- core/repair_cycle.py:91: tests_passed açıklaması açıkça host testlerinin geçtiğini,
  bağımsız kod incelemesi ve bütün görev kabulünün hâlâ beklendiğini belirtir.
  agent_chat.py155-160 başarılı sohbet yanıtına aynı sınırı Türkçe ekler, mevcut
  ajan içeriğini korur; tests/test_chat_repair.py bunu doğrular.

### Güven sınırı (kapanmış güvenlik sandbox'ı değildir)

Yetkili proje kodu test worker'ıyla aynı Python sürecinde çalışır. Nonce/argv
önlemi raporlanan kolay makbuz sahtelemesini engeller; düşmanca Python'un bellek,
frame/global introspection, monkeypatch veya test ortamı müdahalesiyle her türlü
aldatmasını engellediği iddia edilmez. TextTestRunner metni de aynı süreçten gelir.
Dolayısıyla tests_passed = host testleri geçti, bağımsız kod incelemesi bekliyor.
Onarım farkı başka ajan veya kullanıcı incelemeden kabul/merge/kurulum sayılmaz.
UI/model uçlarına yeni keyfi komut yetkisi verilmedi. Canlı kapı3, bağımsız P1
incelemesi kabul edilene kadar kapalıdır.

## P2: support_files

HostUnittestAdapter ve register_host_unittest_plan artık ayrı support_files listesi
alır. JSON/CSV/PDF veya yardımcı Python dosyaları testlerle birlikte ilk ajan
yazımından ÖNCE hash'lenir, dosya adına göre sıralı aynı immutable tuple'a girer;
yalnız test_files çalıştırılır. Destek dosyası otomatik import/çalıştırılmaz.
Yol kaçışı, case-insensitive duplicate, symlink/reparse ve mevcut1MiB/file,
8MiB toplam okuma sınırları destekler için de geçerli. En fazla64 test+64 destek.

```python
chat.register_host_unittest_plan(
    conversation_id, project_id=project_id, provider='codex',
    test_files=('test_invoice.py',), expected_tests=8,
    support_files=('expected.json', 'helpers.py'),
    python_executable=approved_python_path,
)
```

Host bağımlılık listesini doğru seçmek zorundadır; bütün transitive imports,
üretim dosyaları veya harici ortam otomatik korunmuş sayılmaz. Onarılacak üretim
dosyası support_files'a alınırsa değiştirilmesi engellenir; bu liste yalnız sabit
test oracle/yardımcıları içindir. Bilinmeyen oracle bağımlılıkları varsa canlı
plan kabulü öncesi liste tamamlanmalıdır.

## P3

- Belirsiz owned host cleanup hâlâ tüm sohbet admission'ını engeller (güvenli).
  Yeni ret mesajı pending adaptörün sohbet kimliğini gösterir: agent_chat.py667-669.
- expected_tests tam eşitlik değil host alt sınırıdır. tests_run > expected_tests
  kabul edilir; gerçek sayı raporlanır ve output/receipt eşitliği yine zorunludur.
  Daha fazla test, kod incelemesi veya genel görev başarısı yerine geçmez.

## Gerçek kontroller

Komutlar: scripts/run_safe_tests.py [tests.test_host_test_runner,
tests.test_repair_cycle, tests.test_chat_repair, tests.test_agent_chat,
tests.test_multi_agent_service]; tam koşuda modül argümanı yok.
Çalışan Python3.13.17'ye var olan Store site-packages yalnız test process'inde
site.addsitedir ile eklendi; sistem kurulum/PATH/hesap değişmedi.

- Önce:12 test /2.790s / FAILED(failures=1), beklenen P1 yeniden üretimi.
- Nihai4fd3b44 hedefli:59 test /8.597s /OK, skip0, exit0.
- Nihai4fd3b44 tam takım:1652 test /218.567s /OK (skipped=2), exit0.
- Python syntax:359 dosya OK; embedded JS exit0; diff check temiz.
- Yayın denetimi: PASS,601 dosya /1294 history blob /bulgu0.

Yeni testler: gerçek üretim modülü argv sahtelemesi; worker'a eksik/yanlış nonce
makbuzu enjekte edilmesi; doğru nonce fakat output/count uyuşmazlığı; destek
JSON ve yardımcı hash'leri; destek yol kaçışı/duplicate; host tabanından fazla
iki gerçek testin doğru raporlanması. Enjeksiyon testleri sentetik negatif
regresyondur; canlı model veya kullanıcı kabulü olarak sunulmaz.

Ham kanıt repo dışında:
C:\Users\LENAVO\.codex\backups\quartz-review-20261109\host-receipt-before.log
C:\Users\LENAVO\.codex\backups\quartz-review-20261109\host-receipt-frozen-targeted.log
C:\Users\LENAVO\.codex\backups\quartz-review-20261109\host-receipt-frozen-full.log

SOURCE/TESTED; BUILT yok, model/GUI LIVE VERIFIED yok. main/paket/kurulum/push
yapılmadı. Önceki arşiv ve başarısız kanıtlar korundu; özel kullanıcı dosyaları ve
ASTER'e dokunulmadı. Son karar bağımsız Claude incelemesine bırakılmıştır.