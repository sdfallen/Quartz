# Görev Sınavı: görev listesi ve Türkçe anlama seti (5 Kasım 2026)

Dal: `claude/task-exam-tasks-20261105`, taban `92751a3`. Plan: `QUARTZ_COK_GUCLU_PLAN_20261105.md` Bölüm 2.
Durum: **taslak.** Codex ve Gemini eleştirisi bekleniyor. Koşucuya henüz bağlanmadı.

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
