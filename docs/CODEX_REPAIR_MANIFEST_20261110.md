# Claude repair-chat incelemesi sonrası P2/P3

Taban: 057eacb + güncel main belgeleri/poll düzeltmesi. Yeni düzeltme ayrı
codex/repair-loop-20261109 dalında; kurulu sağlık paketi değiştirilmedi.

- RepairCycle.run(require_manifest=True) ilk gözlem dahil manifest zorunlu kılar.
  None/boş/bozuk manifest blocked olur. Beklenen biçim değişmez tuple içinde
  (test_dosyası, küçük harf 64 hex SHA256) çiftleridir. Tüm sonraki gözlemler aynı
  tuple'ı taşımalı. Değişiklik veya kayıp blocked. Host hash'i gerçek dosyalardan
  üretmeli; modelin söylediği hash'e güvenmemeli.
- AgentChat'in bütün register_repair_plan yürütmeleri require_manifest=True
  kullanır. Çekirdek bağımsız kullanımda varsayılan False kalır; sohbet planında
  bunu kapatan IPC/UI/MCP seçeneği yoktur.
- Callback hash'leri koruma altındaki host dosyalarından hesaplamalı; bu kontroller
  gerçek runner/adaptör ihtiyacını ortadan kaldırmaz. İlk agent yazımından önceki
  onaylı host testlerinin başlangıç hash'lerini adapter ayrıca korumalıdır.
- Repair-cycle sonucuyla hata bitişinde son agent içeriği korunur; hata aşağıda
  "Onarım sonucu" bölümüne eklenir. Metadata/status failed kalır; eski içerik
  korunması başarı kabulü değildir. Stop yolu değiştirilmedi.

Doğrulama: python -B scripts/run_safe_tests.py tests.test_repair_cycle
tests.test_chat_repair tests.test_agent_chat tests.test_multi_agent_service →
Ran42 tests in5.346s / OK, skip0. Yeni negatifler: manifest yok; aynı8 test ve
değişen hash; blocked repair sonrası yanıt metninin korunması. Önceki çekirdek
Stop/test-sayısı/cleanup/model kapsam testleri de bu komutta geçti.

Tam suite önceki 057eacb kodu için 1632/2 skip kanıtıyla sınırlıdır; bu küçük
patch için yeniden çalıştırılmadı. SOURCE/TESTED; BUILT/LIVE değil. Yeni main
birleşimi, derleme ve kurulum yapılmadı. Claude'un bağımsız incelemesi beklenir.
S4 reddi korunur. Canlı kapı3, gerçek host adaptörü ve paketli kabul olmadan
tamamlanmış sayılmaz.
