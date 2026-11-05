# P0-3 — bağımsız hedef oracle'ı

`core/task_oracle.py`: host'un yürütme bitmeden bildirdiği, task/run kimliğine
bağlı değişmez dosya postcondition'ları. Destek: tam UTF-8 içerik, SHA256,
olmaması gereken dosya. Boş plan, tekrar planlama, başka task/run, kök dışı
yol ve junction/symlink reddedilir. Okuma 4 MiB ile sınırlı; eşzamanlı değişim
başarı sayılmaz. Beklenen doğru içerik zaten varsa no-op geçerlidir.

`MultiAgentService.register_goal_oracle` yalnız güvenilir host adaptörüne ait;
GUI/MCP aracı değildir. Serbest metinden veya model sonucundan plan türetilmez.
`get_run`, run listesi ve sohbet mesajı projeksiyonu gerçek dosyayı yeniden
okuyarak sonuç alır. Eksik oracle NOT VERIFIED. CLI exit=0/source syntax geçişi
hedef kanıtı değildir. İç komut nonzero olup sonra onarılması veya beklenen
negatif komut, nihai postcondition doğruysa otomatik ret nedeni olmaz.

Host evaluation nesnesi JSON iddiasından ayrıdır; task'e ait olmayan geçmiş
receipt canlı yetki değildir. `goal_verdict=VERIFIED` yalnız bildirilen koşulları
kapsar; `goal_accepted=False` kalır. Semantic/UI görevler için bu dosya adaptörü
uygun değildir ve geçilmiş sayılmaz. CLI ile aynı Windows kullanıcısında çalışan
host, işletim sistemi güvenlik sınırı değildir; tam yetkili koddan kriptografik
yalıtım iddiası yoktur.

IR-CLAUDE-ORACLE-01: Sonuç kartında execution/evidence/goal ayrımını koru;
`goal_evidence.level=HOST POSTCONDITION` ve kapsamını göster. Yetkisiz sohbet
veya model callback'i `register_goal_oracle` çağıramasın. Canlı Görev Sınavı
adaptörü, kullanıcıca seçilen fixture'ın önceden incelenmiş hedef planını
yürütme başlamadan host üzerinden bağlayacak. Mevcut 30 görev henüz bu adaptöre
bağlanmış değildir. Rastgele doğal dil hedeflerine VERIFIED üretme.

TESTED komut: `python -X utf8 -B scripts/run_safe_tests.py tests.test_task_oracle
tests.test_wave2_outcomes tests.test_multi_agent_service tests.test_agent_chat`.
49 test, 0 skip, PASS. Kota mesajı mock negatif vakasından gelir; gerçek model
çağrısı yapılmadı. BUILT / LIVE yok.
