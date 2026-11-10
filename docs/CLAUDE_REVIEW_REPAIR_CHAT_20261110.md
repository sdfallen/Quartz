# Claude incelemesi — repair P2/P3 düzeltmesi ve sohbet bağlantısı (Codex, `057eacb`)

İncelenen: `codex/repair-loop-20261109` `e3eefba` (P2/P3) + `057eacb` (IR-REPAIR-CHAT-01 ilk bağlantı).
Hedefli: `tests.test_repair_cycle tests.test_chat_repair tests.test_agent_chat tests.test_multi_agent_service`
→ `Ran 39 tests`, OK (ayrı worktree, `057eacb`). Tam takımı ben çalıştırmadım.

**Karar: SOURCE/TESTED kabul, bir P2 koşuluyla.** Bağlantı canlı kapı 3'ten (fikstürle gerçek onarım)
önce P2'yi kapatmalı; main'e alınması P2'ye bağlı değil, çünkü plan yalnız host Python'dan kaydediliyor ve
henüz hiçbir yol kaydetmiyor.

## Kapananlar

- P2 (test sayısı düşüşü): `expected_tests` ya da ilk gözlem taban; altına düşünce `blocked`. Doğru.
- P3 (Stop): test/repair istisnasında önce `stop.is_set()` → `cancelled`. Doğru. Sohbet tarafında Stop
  planı siliyor ve `repair_stop`'u kuruyor; iptal edilen turda dış `except` `_is_turn_cancelled` ile
  çıkıyor, "failed" yazmıyor.
- Bağlantı: plan tek kullanımlık, aynı proje/sağlayıcı/model ve yazma izni dispatch'ten önce ve
  çalıştırmada iki kez denetleniyor; her test ve onarımdan önce önceki yazıcının çıkışı
  (`process_exit_confirmed`) bekleniyor; her onarımdan önce checkpoint; test çıktısı "güvenilmeyen veri"
  olarak JSON içinde. IPC/UI'ye uç açılmamış. İstediğim noktaların hepsi var.

## P2 — test dosyası imzası isteğe bağlı; test gevşetilerek "geçti" alınabiliyor

Sayı korunuyor, ama içerik korunmuyor: `test_manifest` verilmezse onarım `assertEqual(total, 118)`'i
`assertTrue(True)`'ya çevirip aynı 8 testle `tests_passed` alır. Prompt'taki "host testlerini değiştirme"
bir istek, engel değil. Belge bunu adaptöre bırakıyor; ama ilk adaptör unutursa sessizce geçer.

İstek: `register_repair_plan` ile kaydedilen planlarda `test_manifest` zorunlu olsun — ilk gözlemde
`None` ise `blocked` ("Host test manifest missing"). Çekirdek `RepairCycle` isteğe bağlı kalabilir
(`require_manifest=True` parametresi yeter). Negatif test: aynı sayı, değişmiş test dosyası → `blocked`;
manifest yok → `blocked`.

## P3

- Onarım `blocked`/`exhausted` bitince dış `except` mesaj içeriğini hata metniyle değiştiriyor; ajanın
  son yanıtı ekrandan gidiyor (`repair_cycle` metadata'sı birleştiği için kalıyor). Kullanıcı neyin
  denendiğini görmeli: içerik korunup hata ayrı satır olarak eklenebilir.
- `register_repair_plan` geçerlilik için boş bir `RepairCycle` kuruyor; zararsız, ama `max_repairs`
  denetimi ayrı bir fonksiyon olsa daha açık.

## Kanıt seviyesi

SOURCE + hedefli birim test. Gerçek model onarımı, paket ve canlı kabul yok (Codex belgesi de böyle
diyor). Canlı kapı 3 P2 kapandıktan, adaptör bağlandıktan ve paket kurulduktan sonra benim
operatörlüğümde.
