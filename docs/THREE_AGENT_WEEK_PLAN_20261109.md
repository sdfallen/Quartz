# Üçlü çalışma planı ve Codex'e devir — 9 Kasım 2026

Hazırlayan: Claude. Kullanıcı kararı (9 Kasım akşamı): Codex döndü; Quartz'ı Codex, Gemini (Antigravity)
ve Claude birlikte, paralel geliştirecek. 6 Kasım geçici devri bu belgeyle biter.

## 1. Hedef (16 Kasım)

Kullanıcının sorusu: "Bu haftanın sonunda Quartz projeleri geliştirebilen otonom bir seviyeye gelir mi?"
Dürüst hedef **gözetimli otonom kod geliştirme**:

> Küçük/orta boy işte kullanıcı görevi verir; Quartz yazar, test eder, gerekirse kendisi düzeltir,
> inceletir ve kanıtla raporlar. Kullanıcı onaylar.

Saatlerce kendi başına proje geliştiren sistem bu haftanın hedefi değildir. Masaüstü sınavlarının kalanı
(Dosya Gezgini, tarayıcı, UAC, çoklu pencere) ikinci plandadır.

**Bitti sayılması için (hafta sonu kabul kapısı):**

1. Bozuk ortamda (Python yok/takma ad bozuk, Squad bağlı değil, CLI girişi yok) görev başlamadan nedeni
   Türkçe söylenir; ajan sessizce bozulmaz.
2. Testleri başarısız bırakan bir yazıcı turunda Quartz, aynı yazıcıya hata çıktısıyla en çok N tur daha
   verir; her tur checkpoint'li, Durdur her an çalışır. Tohumlanmış bir fikstürde insan müdahalesiz geçer.
3. long-01/02 ve çok dosyalı (5–10 dosya) gerçek bir özellik paketli Quartz'ta canlı koşulur.
4. Quartz'ın kendi deposunda küçük, gerçek bir iş tek mesajla, testi geçmiş ve incelenmiş çıkar.
5. desk-09 (Durdur ≤ 1 sn, Durdur sonrası girdi yok) regresyon koşusu yeşil kalır.

## 2. Durum (9 Kasım 22:50)

- `main` = `cb962b7`. Kurulu `dist\Quartz\Quartz.exe` = `a176728d195276fbd5a7894ea3f8e181815619716566a075a8622cf810545b7b`
  (yardımcı `94e40e5e…`, değişmedi). GitHub'a gönderim yok.
- Son tam güvenli suite (`cb962b7` adayı): 1590 vaka, OK (skipped=2). Paket doğrulaması 88/88.
- Bilgisayara python.org Python 3.13.17 (kullanıcıya özel, `py` başlatıcısıyla) kuruldu; kullanıcı PATH'inde
  Store takma adından önce. Kod değişikliği değil, ortam değişikliği.

### 9 Kasım canlı sınav (paketli Quartz, gerçek ajanlar)

| Görev | Sonuç | Kanıt |
|---|---|---|
| exam-desk-09 | **VERIFIED** — HUD Durdur tıklamasından yetki kaldırılmasına 0,701 sn; Durdur sonrası girdi yok; overlay kapandı | `C:\QuartzExam\host\exam-desk-09-20261109-211340\grade.json` |
| exam-code-03 | 4/4 makine kontrolü (tek yazıcı codex, inceleyici yan etkisiz, test geçiyor); **insan puanı bekliyor** | `C:\QuartzExam\host\exam-code-03-20261109-223644` |
| exam-desk-03 | FAILED — ekran 69.104, yanıt doğru; 154,7 sn; `fresh_snapshot_after_last_input` başarısız (bkz. §4 S1) | `C:\QuartzExam\host\exam-desk-03-20261109-215905` |
| exam-code-07 | Ölçülemedi — Gemini 20 dosyayı tek komutla saniyeler içinde değiştirdi, Durdur'a pencere kalmadı; harness'in sohbet içi Stop tıklaması da WebView'a ulaşmadı (bkz. §4 S2) | `C:\QuartzExam\host\exam-code-07-20261109-212349` |

Ölçüm notu: desk-09 için Durdur, fikstürün ilk karakteri raporladığı anda bir host betiğiyle HUD'a
tıklandı; `stop_at` tıklamadan önce yazıldı (gecikme Quartz'ın aleyhine sayılır). HUD sinyal yolu ayrıca
ölçüldü: tıklamadan geri çağrıya 0,02–0,03 sn.

## 3. Bağımsız inceleme bekleyen değişiklikler (öncelik sırasıyla)

Codex'in 9 Kasım incelemesi `0fb2b2e`'ye kadardır. Sonrasında Claude'un üç birleşimi **bağımsız incelemesiz**
(kullanıcının "düzelt / kur" talimatlarıyla, testli ve canlı denenmiş) main'e girdi:

1. **`cb962b7`** (`claude/key-sequence-20261109`, 1 commit) — girdi güvenliğine dokunur.
   `desktop_act action=key` boşlukla ayrılmış en çok 24 SAFE_KEYS tuşu taşır; `+ - * / = . ,` eklendi ve
   sayısal tuş takımına eşlenir (Türkçe Q klavyede `*` başka karaktere dönüşüyordu). `broker.stop()` kilidi
   beklemeden `_input_cancel` bayrağını kaldırır; dizi her tuştan önce bayrağa ve ön plana bakar, kalan tuşları
   göndermez. `grant()` bayrağı temizler. Araç şeması yardımcı exe'de olduğu için öğretim
   `natural_desktop.INSTRUCTIONS`'tadır. İncelenecek risk: iptal bayrağının yaşam döngüsü (stop → grant
   arası), `hold`'un tek tuşta kalması, sayısal tuş eşlemesi.
2. **`826f846`** (`claude/stop-lock-chain-20261109`, 1. commit) — Codex dosyası `core/natural_desktop.py`.
   `status()`, bekçi döngüsü ve `task_context` broker'ı görev kilidi dışında okur (broker bir eylem boyunca
   kilidini tutar; Durdur o eyleme kuyruklanıyordu). Bekçi, okuduğu bağlantı nesnesi değişmediyse durdurur.
   UI: masaüstü görevinin ara satırları (`task_status` starting/running/waiting_for_inline_permission) rozetsiz;
   terminal `task_status` Durduruldu/Başarısız/Engellendi rozetini belirler.
3. **`095e71c`** (`claude/stop-lock-chain-20261109`, 2. commit) — `advanced_controller.smart_open`:
   `calc`, `calc.exe`, `Hesap Makinesi`, `Not Defteri` vb. doğrudan açılır; `_search_dir_limited` artık
   bakılan dosya (2000) ve süre (1,5 sn) ile sınırlı (eski sınır yalnız eşleşmeyi sayıyordu; Masaüstü
   taraması boşta 13 sn sürüyordu).

Her birinin commit mesajı canlı ölçümü ve test sayısını içerir. Yeni testler: `tests/test_stop_lock_chain.py`,
`tests/test_smart_open_fast.py`, `tests/test_key_sequence.py`, `tests/test_gui_wave2_status.py` (ek vaka).
Kilit testleri düzeltme olmadan başarısız olduğu doğrulandı.

## 4. Açık bulgular

- **S1 (Codex, sınav aracı):** `fresh_snapshot_after_last_input` yalnız ayrı bir `desktop_observe` kabul ediyor.
  Broker her `desktop_act`'tan sonra kendi gözlemini alıyor ve ajan `desktop_verify`'ı o gözlemle yaptı.
  Kural ya bu eylem sonrası gözlemi kabul etmeli ya da gerekçesi belgelenmeli. Claude kuralı değiştirmedi.
- **S2 (Codex, sınav aracı):** code-07'nin "ilk değişiklikten 10 sn sonra Durdur" kuralı hızlı yazıcıda
  ölçüm yapamıyor. Canlı koşu için `process_tree_gone_seconds`, `stop_receipt_confirmed`,
  `checkpoint_restored_matches_baseline` işaretlerini üreten bir yol da yok. Öneri: yavaş/adım adım yazdıran
  fikstür ve barrier'ın yazdığı işaretler. Not: sentetik `mouse_event` tıklaması tk HUD'da çalıştı, WebView2
  içindeki "Görevi durdur" düğmesinde çalışmadı.
- **S3 (Claude, UI):** Kristal, mod yalnız Antigravity iken de boşta "BİRLİKTE" yazıyor; code-03'ün ilk
  denemesi bu yüzden tek ajan modunda koştu.
- **S4 (Gemini, runtime/Squad):** Fikstür projelerinde "Squad: Bağlantı Sorunu"; seçili proje
  `exam-code-03` iken masaüstü görevi "Seçili projenin mevcut Squad bağlantısı hazır değil" ile hiç başlamadı.
  Squad Pilot'ta sorun yok. Fikstürdeki eski `.squad` klasörü şüpheli; incelenmedi.
- **S5 (ortam):** Ajanların `python` komutu Store takma adında aralıklı `[Errno 22]` veriyordu (Codex
  `danger-full-access` iken de). Düz koşu, Job Object, Quartz ortamı ve eşzamanlılıkla yeniden üretilemedi;
  python.org Python kurulumundan sonra Codex testleri kendisi geçirdi. Gemini tarafı yeniden gözlenmedi.
- **S6 (hız):** desk-03'ün kalan 155 sn'si çoğunlukla model bekleme (ilk araç çağrısına 56 sn, odağa 50 sn).
- İnsan puanı bekleyenler: exam-chat-01, exam-code-03, exam-code-05, exam-code-09.

## 5. İş bölümü (10–16 Kasım)

Ortak kurallar aynen: ayrı worktree/dal, başka ajanın dosyasına yazma yok (integration request), gerçek
masaüstünde aynı anda tek operatör, GitHub gönderimi yok, kanıt seviyeleri ayrı (SOURCE/TESTED/BUILT/LIVE).
**Kimse kendi üretim kodunu kendisi kabul etmez:** her üretim dalı diğer ikisinden birinin incelemesinden
sonra birleşir.

| Ajan | Sahip olduğu iş | Dosya alanı |
|---|---|---|
| **Codex** | (a) §3 geriye dönük inceleme, önce `cb962b7`. (b) **Otomatik düzeltme döngüsü** (kabul kapısı 2): test başarısızsa aynı yazıcıya hata çıktısıyla en çok N tur, checkpoint'li, Durdur'a bağlı, kanıta yazılı. (c) Sınav aracı S1/S2. (d) `main` birleştirme ve kullanıcı onaylı kurulum yeniden Codex'te. | `core/agent_chat.py`, `core/multi_agent_service.py`, `core/natural_desktop.py`, `core/run_evidence_store.py`, `core/workspace_checkpoint.py`, `scripts/exam_*.py`, `docs/task_exam/*` |
| **Gemini** | (a) **Ortam sağlık kontrolü** (kabul kapısı 1): görev öncesi Python yürütülebilirliği (Store takma adı dahil), Git, Squad bağlantısı, CLI girişi; yapılandırılmış sonuç. (b) S4 Squad bağlantı sorunu. (c) Claude'un yeni dallarının bağımsız incelemesi. | `core/codex_runtime.py`, `core/antigravity_runtime.py`, `core/process_tree.py`, `core/squad_adapter.py`, yeni `core/environment_health.py` |
| **Claude** | (a) S3 ve sağlık kontrolünün arayüz yüzü (Gemini'nin sonucunu gösteren kart/uyarı). (b) **Canlı operatör**: kabul kapısı 3–5 koşuları (long-01/02, çok dosyalı özellik, Quartz'ın kendi deposunda gerçek iş, desk-09 regresyonu). (c) Masaüstü broker/native sahipliği sürer. (d) Codex dallarının bağımsız incelemesi. | `ui/*`, `assets/*`, `gui.py` arayüz kısmı, `core/desktop_broker.py`, `core/desktop_native.py`, `advanced_controller.py` |

Sıra ve bağımlılık:

- 10 Kas: Codex §3 incelemesi; Gemini sağlık kontrolü taslağı; Claude S3.
- 11 Kas: Codex düzeltme döngüsü; Gemini sağlık kontrolü + S4; Claude sağlık kontrolü UI'si (Gemini'nin
  sonuç biçimine integration request ile bağlanır).
- 12 Kas: Birleştirme turu (Codex), paket + kurulum (kullanıcı onayıyla); Claude canlı: düzeltme döngüsü
  tohumlanmış fikstür, long-01/02.
- 13 Kas: Claude canlı: Quartz deposunda gerçek iş. Çıkan hatalar sahiplerine.
- 14 Kas: Düzeltmeler + desk-09 regresyonu.
- 15–16 Kas: Son paket, durum raporu, sürüm notu; GitHub yalnız kullanıcı onayıyla.

Canlı masaüstü koşuları aynı anda tek ajan tarafından yapılır (varsayılan Claude). Codex/Gemini canlı koşu
gerektirirse kullanıcıya kayıt eder.
