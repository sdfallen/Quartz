# Görev Sınavı: görev listesi ve Türkçe anlama seti (5 Kasım 2026)

Dal: `claude/task-exam-tasks-20261105`, taban `92751a3`. Plan: `QUARTZ_COK_GUCLU_PLAN_20261105.md` Bölüm 2.
Durum: **taslak v2 (6 Kasım).** Codex ve Gemini eleştirileri işlendi; koşucuya henüz bağlanmadı. Değişiklikler en altta.

## Dosyalar

- `docs/task_exam/tasks_20261105.json`: 30 görev. Her biri kapı, gereken izin (hesap/masaüstü), ajan modu, hazırlık,
  kullanıcı mesajı, başarı koşulları ve başarısızlık nedenleri taşır. Komut değil veridir.
- `docs/task_exam/intent_corpus_20261105.json`: G5 için 78 Türkçe/İngilizce cümle ve beklenen yönlendirme.

## Görevlerin dağılımı

| Grup | Adet | Ne ölçer |
|---|---:|---|
| Sohbet ve devam (`exam-chat-*`) | 3 | Sohbetin işlem başlatmaması, "devam et"in aynı göreve gitmesi |
| Kod (`exam-code-*`) | 7 | Gerçek düzeltme, tek yazıcı, olmayan dosyada dürüstlük, sözdizimi hatasında yanlış başarı, Durdur, ekip incelemesi |
| Masaüstü (`exam-desk-*`) | 14 | Not Defteri, test uygulaması, Hesap Makinesi, Dosya Gezgini, iki pencere, yerel web sayfası, odak değişimi, izinsiz pencere, Durdur, izin reddi, UAC, kapanan pencere, takılma, Gemini operatör |
| Süreklilik (`exam-long-*`) | 3 | 20+ dakikalık görev, çökme sonrası temizlik, yeniden açılışta sohbet hafızası |
| Öğrenme (`exam-learn-*`) | 2 | İkinci koşuda adım azalması, sürüm değişince eski bilginin uygulanmaması |
| Maliyet (`exam-cost-01`) | 1 | Boşta model çağrısı ve süreç sayısı |

Kapı kapsamı (bir görev birden fazla kapıyı ölçebilir): G1 10, G2 8, G3 9, G4 5, G5 3, G6 2, G7 2, G8 2.
G5'in asıl ölçümü anlama setidir. G9 kişisel kullanım kararı gereği dışarıda.
Gereken izinler: 18 görev hesap ve masaüstü, 11 görev yalnız hesap, 1 görev yalnız masaüstü ister. Hepsi canlı koşu gerektirir.

## Başarı koşulu ilkeleri

- **Modelin sözü sayılmaz.** Koşullar dosya özeti, test komutu, UIA metni, test uygulamasının durum dosyası,
  süreç listesi ve Quartz'ın kendi kayıtlarından (yazıcı kaydı, Durdur makbuzu, broker denetim kaydı) okunur.
- **`reply_*` koşulları zayıftır.** Yalnız bir sayı veya sabit metin aranabiliyorsa geçerlidir (`reply_contains`).
  "Dosyanın olmadığını söyledi" gibi yorum isteyen koşulları (`reply_states_*`, `reply_does_not_claim_success`)
  bir insan veya ayrı bir değerlendirici işaretler; otomatik VERIFIED sayılmaz.
- **Gizli varyantlar:** Repo herkese açık olduğu için gizli görev burada tutulamaz. `exam-code-06`'nın 10 hatalı varyantı
  ve diğer görevlerin değişik sürümleri repo dışında, uygulamayı yazmayan bir ajanda durur. Öneri: Gemini.

## Koşucuya bağlama (Codex için)

Mevcut koşucu yalnız `regression` ve incelenmiş `script` adaptörlerini çalıştırıyor; bu görevler için canlı sohbet adaptörü gerekir.
JSON'daki 65 koşul adı birkaç aileye ayrılır; her aile bir doğrulayıcıdır:

| Aile | Örnek koşullar | Kaynak |
|---|---|---|
| Dosya | `file_text_equals`, `file_sha_unchanged`, `changed_files_subset`, `no_files_created`, `directory_exists` | Fixture klasörü |
| Test/kod | `command_passes`, `python_compiles` | Fixture içinde incelenmiş sabit komut |
| Yazıcı/Durdur | `writer_claim_released`, `single_writer`, `stop_receipt_confirmed`, `checkpoint_*` | `.quartz/writer_claims.json`, Durdur makbuzu |
| Girdi denetimi | `inputs_only_to_approved_windows`, `no_input_events_after_stop`, `permission_card_shown_before_input` | Broker denetim kaydı ve görev `result.json` |
| Süreç | `no_orphan_processes_after_seconds`, `process_tree_gone_within_seconds`, `process_spawns_at_most` | Süreç listesi |
| UI | `uia_text_contains`, `fixture_state`, `overlay_hidden` | UIA, test uygulaması durum dosyası |
| Görev durumu | `status_*`, `same_task_id_continues`, `task_marked_interrupted` | Görev kaydı ve sohbet deposu |
| Öğrenme | `step_reduction_at_least_percent`, `old_knowledge_not_applied_to_new_hash` | Uygulama bilgisi deposu, adım sayısı |
| Yanıt | `reply_contains`, `reply_states_*` | Sohbet deposu (yorum isteyenler insan işareti) |

Bilinen ön koşullar:
- `scripts/desktop_acceptance_fixture.py` durum dosyasını repo içine (`labs/`) yazıyor; adaptör bunu fixture klasörüne yönlendirmeli.
- `exam-desk-11` için yönetici isteyen zararsız bir test EXE'si, `exam-long-01` ve `exam-learn-02` için test uygulamasının
  300 satırlı ve sürümü değişmiş varyantları yok; yazılmaları gerekiyor.

## Türkçe anlama seti: ilk ölçüm

Etiketler ölçümden önce yazıldı. Kaynak `92751a3`, yalnız `message_intent` ve `desktop_intent` çağrıldı (SOURCE/TESTED, model yok).

| Grup | Doğru |
|---|---:|
| Sohbet | 27/28 |
| Kod görevi | 21/23 |
| Masaüstü görevi | 17/21 |
| Devam/durdur | 5/6 |
| **Toplam** | **70/78 (%89,7)** |

G5 hedefi %95. Yanlışlar:

- **Kritik (G5 engeli):** `c23` "Chrome'u açabilir misin diye soracaktım ama gerek yok" bilgisayar kontrolü olarak yönleniyor.
- **Türkçe karakter olmadan yazım:** `t10` "testleri calistir", `t11` "hatayi duzelt" sohbet sayılıyor. Buna karşılık
  `d13` "chrome u acip youtube a gir" doğru yönleniyor.
- **Listede olmayan uygulamalar:** `d09` Aseprite, `d10` VS Code, `d11` Paint görev sayılıyor ama bilgisayar kontrolüne yönlenmiyor.
- **Eksik fiil:** `d18` "Pencereyi büyüt" sohbet sayılıyor.
- **Devam:** `k04` "tamam devam" devam komutu sayılmıyor.

Set 78 cümleyle küçük bir başlangıçtır; plan en az 300 cümle öngörüyor. Yeni cümleler gerçek sohbet kayıtlarından
kişisel veri çıkarılarak eklenmeli. Bu düzeltmeler `message_intent.py` ve `desktop_task_ui.py`'de, Codex'in Dalga 3 işidir.
Ölçüm, düzeltme için cümleye özel kural yazmayı haklı çıkarmaz; gizli bir cümle seti kabulde ayrıca ölçülür.

## v2 değişiklikleri (6 Kasım 2026)

Kaynaklar: `CODEX_TASK_EXAM_REVIEW_20261105.md` ve `ANTIGRAVITY_WAVE2_HARDENING_AND_REVIEW_20261105.md` bölüm 6.
Liste 30'dan 35 göreve çıktı; JSON `schema_version` 2.

**Ortak kurallar (`common`):** ayrı sınav profili; her beklenen metin, sayı ve dosya adı koşu başına üretilen rastgele değer
(`<nonce>`); oracle durumu modelin yazamayacağı yerde; GUI görevi ajanın aynı işi kabukla yapmasıyla geçilmez;
yorum isteyen koşullar `human_grade` olarak ayrı kaydedilir ve tek başına VERIFIED üretmez (7 görevde var);
bekleme, gözlem, model turu ve gerçek girdi ayrı sayılır. Canlı adaptör önceliği: `exam-code-01`, `exam-chat-01`, `exam-desk-02`.

**Yeni görevler:**

| Görev | Ne ölçer |
|---|---|
| `exam-code-08` | Birlikte modunda Gemini erişilemezken tur kısmi/başarısız sayılır, doğrulanmış sayılmaz |
| `exam-code-09` | Geçemeyecek bir testte ajan ne derse desin hedef doğrulanmaz |
| `exam-code-10` | Salt okunur inceleme dosya değiştirirse koşu başarısız ve ihlal kaydı var (tespit, önleme değil) |
| `exam-desk-15` | Yanıtsız izin kartı 12 dakika bekler: görev duraklar, girdi ve model turu yok, eski kart onaylanamaz, yeniden onay sonrası yeni gözlemle devam |
| `exam-prov-01` | Sağlayıcı hata türleri, çevrimdışı test modülüyle (`tests.test_provider_failure_taxonomy`) |

**Düzeltilen görevler:**

- `reply_states_*` ve `reply_does_not_claim_success` kaldırıldı; yerine yapılandırılmış alanlar (`goal_verdict`, izin kararı olayı,
  durma nedeni) ve `human_grade`.
- `exam-code-04`: davranış testi eklendi; derleme hatası yolu çevrimdışı ayrı fixture'da (`exam-code-04-neg`) sınanıyor.
- `exam-code-06`: bulgu biçimi sabit (`BULGU: <dosya>:<satır> — <neden>`); eşleşme hunk aralığı ve neden sınıfıyla; gizli varyantlar Gemini'de.
- `exam-code-07`, `exam-desk-09`, `exam-desk-12`: sabit süre yerine host bariyeri (ilk dosya değişimi, ilk karakter, ilk girdi).
- `exam-desk-01`: BOM ve satır sonu normalleştirmesi; GUI girdisinin dosya değişiminden önce kaydı.
- `exam-desk-03`: pencere başlığı yerine `CalculatorApp.exe` ve UIA `CalculatorResults`; basamak ayırıcı normalleştirmesi.
- `exam-desk-07`: son tıklama sayısı yerine sıralı olay listesi.
- `exam-desk-08`, `exam-desk-10`: Tam Yetki otomatik onayıyla çelişmemesi için elle onay profili.
- `exam-desk-13`: takılma denetiminin tetiklenmesi zorunlu değil; düğmenin devre dışı olduğunu görüp duran ajan geçer.
- `exam-long-02`: yalnız sınavın kendi Quartz süreci, oluşturma tanıtıcısıyla ve açık kullanıcı izniyle kapatılır.
- `exam-long-03`: sabit `4471` yerine rastgele değer; yalnız sohbet hafızasını ölçtüğü açıkça yazıldı.
- `exam-learn-01`: üç + üç eşleştirilmiş koşu; %30 azalma kalite hedefi, girdi ve gözlem sayısı üzerinden.
- `exam-cost-01`: sayısal öneri eşikler (600 saniyede en çok 30 süreç başlatma, ortalama işlemci %2); ilk koşudan önce kullanıcı onaylar.
