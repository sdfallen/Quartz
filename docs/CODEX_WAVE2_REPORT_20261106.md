# Quartz Dalga 2 — Codex teslimi

5 Kasım talimatı; kapanış 6 Kasım 2026, Europe/Istanbul.
Başlangıç main `1a18556`. Üretim kodunun son commit'i `d23fc0e`.
Bu raporun sonraki belge commit'i kod/test/script baytlarını değiştirmez;
kesin final main SHA ve artifact hash'leri özel delivery receipt'tedir.

**Karar:** Codex backend çalışmaları SOURCE/TESTED teslimidir. Claude UI/broker
entegrasyonu ve gerçek paketli G1–G4 kabulü açık; Dalga 2 bütünü LIVE COMPLETE
değildir. GitHub push, Quartz açma, yeni paket derleme/kurma yapılmadı.

## Sıra ve SHA'lar

| Adım | SHA | Teslim / karar |
|---|---|---|
| 1a | `393f327` (merge `f73ab81`) | Gemini AsyncSnapshot completion TTL + iki test modülü kabul; 7 test PASS. |
| 1b | `ce45c31`, `577c264` | Eski koşucu entegrasyonu, B1/B3 düzeltmesi; 14 hedefli test PASS, iki gerçek Windows child fixture dahil. |
| 2 | `e6cc681` | Ortak execution/evidence/goal/partial sözleşmesi; 29 hedefli test PASS. |
| 3 | `8aa5278` | 78 satır corpus + genel Türkçe kurallar; 36 test PASS. |
| 4 | `99e82d0` | Idle Squad cache, DB/WAL invalidation; 32 hedefli test PASS; 600 s önce/sonra ölçüm. |
| 5 oracle | `7ea2ac4` | Host-declared postcondition, gerçek dosya doğrulaması; 49 hedefli test PASS. |
| 5 pause | `f002c01` | Scope/UAC pause, CLI drain, fresh reissue; 97 hedefli test PASS. |
| 6 | `3f0fe3b` | 30 görev eleştirisi + dar live-chat adapter tasarımı. |
| Regresyon | `e0f25e3` | Eski beklentileri hizalama, Squad-delivery yanlış başarı fix; 61 + 24 hedefli test PASS. |
| Stop regresyonu | `d23fc0e` | Uzun controller Stop kilidini tutmaz; 70 ilgili test + son sınır testi PASS. |

Hedefli sayılar bağımsız koşulardır; toplanıp benzersiz test sayısı olarak
sunulmaz. Bazı erken koşularda import edilen eski TestCase tekrarları vardı;
son tam suite'te yeni eklenen bu tekrarlar kaldırıldı.

## Kod bulguları ve kapanış

| Bulgu | Kaynak | Sonuç |
|---|---|---|
| B1: sıfır/all-skipped test veya stdout'taki sahte summary | `scripts/task_exam_runner.py:70` | stderr summary şartı + gerçekten koşmuş test >0; unknown adapter NOT VERIFIED. |
| B3: normal parent exit sonrası child kalması | `scripts/exam_process.py:21`, `:45`; runner `:87` | Create-suspended + kernel job sahipliği; descendant temizliği belirsiz/kalmışsa BLOCKED. Çift Ctrl+C cleanup'ı yarıda bırakmaz. |
| İstenen iki ajandan birinin hatasını OR ile örtme | `core/agent_chat.py:1749`; `core/task_outcome.py:25` | İlk, ikinci ve devam turlarında participant sonuçları AND; karışık sonuç partial. |
| Başarılı metin üretiminden sonra Squad send hatasının örtülmesi | `core/agent_chat.py:1693`, `:1896` | Yeni test önce completed != partial FAIL; exception yolu state'i de fail yapar. |
| Kaynak/CLI sonucunun hedef kabulü sanılması | `core/task_outcome.py:4`, `core/multi_agent_service.py:108` | Bütün aktif backend projeksiyonları ortak outcome; Squad completion da goal verdict'i ayrı yazar (`:882`). |
| G5 geri çekilen talebin kontrol başlatması | `core/message_intent.py:14` | Son niteliksiz withdrawal iptal eder; farklı nesneye bağlı istisna iptal etmez. |
| Boşta tekrar Squad CLI başlatma | `core/multi_agent_service.py:315` | Sadece display cache; izin/dispatch otoritesi değildir. |
| Modelin kendi hedefini doğrulaması | `core/task_oracle.py`, service `:87`, `:101` | Host'un önceden bildirdiği immutable task/run/file koşulları; JSON/model iddiası oracle olamaz. |
| Yanıtsız izin expiry'sinin görevi bitirmesi | `core/natural_desktop.py:217`, `:238`, `:272`, `:1261` | Awaiting approval, revoke/drain, yeni generation/identity/observation; expired callback grant oluşturmaz. |
| Bu değişiklikte bulunan uzun controller Stop gecikmesi | `core/natural_desktop.py:830`, `:840` | Başarısız testle üretildi; composite çağrı kilit dışı, kısa native girişler serileştirilmiş. Inflight sırasında manuel kart açılmaz. |

Goal oracle ilk dilimde tam dosya text/hash/absence ile sınırlı. Serbest doğal
dil/UI hedeflerinin tümü otomatik VERIFIED olmaz. No-op doğru olabilir;
beklenen nonzero komut, son koşullar doğruysa otomatik ret değildir.
`goal_accepted=False` kullanıcı kabulünü modelden ayırır. Controller'a daha önce
girmiş etkiler geri alınmış gibi gösterilmez; Stop/inflight receipt ayrıdır.

## Ölçümler

- Corpus: **70/78 → 78/78**; critical conversation→desktop yanlışlığı **1→0**.
  Bu 78 seed vaka tam G5'in 300+ holdout kabulü değildir.
- Gerçek idle önce: `577c264`, **600.000 s**, 592 poll, Squad140/Codex4/agy6,
  toplam **150**. Sonra: `99e82d0`, **600.001 s**, 591 poll,
  Squad12/Codex4/agy6, toplam **22**. Her ikisinde model start0.
- Toplam process-start azalması **%85,3**, Squad için **%91,4**. CPU/RAM/FPS
  veya aynı anda yaşayan process sayısı ölçülmedi. Gerçek CLI sorgulu headless
  API koşusu; paketli GUI cost-01 kabulü değildir. Capture kapalı.
- Nihai cache fonksiyonları ile ölçülen `99e82d0` AST hash'leri aynı:
  özel `cache-body-provenance.json`. Tüm son kaynak için eski ölçüm iddiası yok.

Sayaç sınırı: özel collector `Popen.__init__` çağrısını constructor tamamlanmadan
sayar; başarılı spawn ile başarısız başlatma girişimi ayrı kaydedilmedi. Bu
yüzden 150→22 ve 140→12 kesin olarak **Popen başlatma çağrısı/girişimi** azalmasıdır;
bağımsız PID census veya garantili başarılı süreç sayısı olarak yorumlanmamalı.
Ham JSON'daki `actual_subprocess_starts` alan adı bu sınırlamayı değiştirmez.

## Kontrol komutları ve gerçek çıktılar

Özel kanıt kökü: `%USERPROFILE%\.codex\backups\quartz-wave2-20261105`.
Ham loglar, ekran ve kullanıcı verisi repoya eklenmedi.

| Komut | Kapsam / çıktı | Kanıt |
|---|---|---|
| `python -X utf8 -B scripts/run_safe_tests.py` (live tool env kaldırıldı) | Step1 main: 1335 vaka, skip2, OK | `step1-full.log` |
| Aynı komut | İlk yeni tam koşu: 1391, failure4, skip2; eski beklentiler düzeltildi | `wave2-full.log` |
| Aynı komut | `e0f25e3`: 1366, skip2, OK | `wave2-full-final.log` |
| Aynı komut | `d23fc0e`: 1367, error1, skip2; dış fixture cleanup WinError5 | `wave2-final-source-suite.log` |
| Aynı komut, aynı son kaynak | `d23fc0e`: 1367 vaka, **1365 başarılı / 2 skip**, OK; 210.402 s | `wave2-final-source-recheck.log` |
| `python -X utf8 -B scripts/run_safe_tests.py tests.test_registered_search_worker.RegisteredSearchWorker.test_no_match_is_real_exit_one_with_empty_output_and_not_fabricated_matches` | 1 test OK, 4.530 s; kök neden fix sayılmaz | `registered-search-recheck.log` |
| `python -X utf8 -B scripts/check_python_syntax.py` | Published Python syntax: 325 files OK | `syntax-final.log` |
| `python -X utf8 -B scripts/check_gui_javascript.py` | Embedded JS exit: 0 | `javascript-final.log` |
| `python -X utf8 -B scripts/audit_publish.py --staged --history` | PASS, findings0 (nihai belge sonrası tekrar) | `audit-final.log` |
| `python -X utf8 -B scripts/task_exam_runner.py --manifest docs/task_exam_manifest.example.json --output <private-new-dir> --execute --package <installed-Quartz-dir>` | 2/2 TESTED VERIFIED; regression 1.848 s, synthetic process 3.183 s; steps=null | `runner-final.log`, `runner-final/result.json` |
| `git diff --check` / `git diff --cached --check` | exit0 | teslim terminal kaydı |

BUILT: Quartz paketi derlenmedi. Var olan helper yalnız test worktree'sine
kopyalandı; SHA `350d7ae4…71fcbad`, önceki doğrulanmış helper ile aynı.
LIVE VERIFIED: gerçek Quartz/chat/account/desktop kabulü yapılmadı. Gerçek
Windows child process fixture'ları TESTED'dır, GUI kabulü değildir.

## Claude/Antigravity teslim sınırları

1. `WAVE2_RESULT_CONTRACT_20261105.md` — `IR-CLAUDE-OUTCOME-02`:
   execution_only / goal / partial rozetleri.
2. `WAVE2_TASK_ORACLE_20261105.md` — `IR-CLAUDE-ORACLE-01`:
   scope'u doğru gösterme, trusted adapter kaydı; modelden oracle alma yok.
3. `IR_CLAUDE_APPROVAL_PAUSE_20261105.md` — expired kart reissue, cleanup
   hazır olana kadar onayı bekletme, restart context, Stop/UAC/fresh identity.
4. `IR_AGY_TOOL_FIXTURE_CLEANUP_20261106.md` — mevcut registered-search
   Windows cleanup flake. Tek başına tekrar PASS, kalıcı neden UNKNOWN.

Broker, Native, UI, gui.py ve provider runtime dosyaları bu Codex değişiminde
değiştirilmedi. Gemini'nin yalnız incelenmiş AsyncSnapshot/test teslimi alındı.
Başka yeni Claude/Gemini dalı incelenmeden birleştirilmedi.

## Açık kalanlar / kabul kararı

- UI/Broker tarafında integration request'ler tamamlanmadan izin deneyimi
  ürün düzeyinde bitmiş değildir; expired kart yeni backend API'sine bağlanmalı.
- 30 sınav görevi eleştirildi; gerçek ana-sohbet adaptörü **tasarım**, çalışan
  live adapter değil. Gerçek hesap/masaüstü testleri için izin/tek operatör
  slotu gerekir; bu oturumda yapılmadı.
- G1–G4 gerçek paket, uzun görev, gerçek UAC/odak/Stop gecikmesi ve crash
  kabulü açık. Yeni seed başarı oranı bu kapıları kapatmaz.
- Windows fixture cleanup flake ayrı açık IR'dir; yeşil tekrar çıkarsa bile
  “kalıcı düzeltildi” yazılmaz. Başarısız log korunur.
- Kurulu EXE SHA256 **4a42e09dde30286e7c3626aa80e677650d946891e50fce2679c53cc0595238ce**,
  kaynak **1a18556** olarak kaldı. Yeni main ile aynı paket değildir.

## Koruma ve geri alma

Orijinal checkout'un dalı/dirty dosyaları değiştirilmedi. Çalışma ve ölçüm ayrı
`%USERPROFILE%\.codex\worktrees` altındadır. `.env`, kullanıcı sohbet/ayarları,
korunan save ve ASTER dosyaları üzerinde işlem yok. Assets/gui/UI/Broker/Native
ve runtime dosyalarında başlangıca göre diff0 (Gemini async snapshot istisnası).
Kullanıcı verilerinde yapılmamış byte-hash denetimi için diff0 iddiası yok.
Kurulu EXE hash'i gerçek dosyadan tekrar okundu; değişmedi. Push/kurulum yok.

Yedek: `before-wave2.bundle`; final bundle + arındırılmış kanıt özeti özel
teslim dizinindedir. Geri alma gerekirse yeni bir worktree/dal başlangıç
`1a18556` referansından açılır ve kontrol edilir; kirli kullanıcı checkout'u
resetlenmez. Main üzerinde tarih koruyan revert gerekirse yalnız Codex,
feature commit'lerini ters sırada, iki merge'i `git revert -m 1` ile geri alır.
Bu oturumda geri alma uygulanmadı; kurulu paket zaten değiştirilmedi.
