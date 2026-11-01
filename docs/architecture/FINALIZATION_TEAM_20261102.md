# Quartz mimari kapanışı — üçlü sahiplik

Tarih: 2026-11-02. Kullanıcı mevcut çalışmayı checkpoint edip Codex, Claude ve Antigravity arasında yeniden bölmemizi istedi. Bu belge önceki TEAM.md dosyasının bu dilimle çakışan dosya sahipliğinin yerini alır; tarihsel teslimleri silmez.

## Başlangıç ve ayrılmış çalışma alanları

- Önceki birleşik baseline: `eb407805c2f5667d026d57bba095e732e71a0018`.
- Doğrulanan yeni frontend dilimi: `bd38bf2fe4d83d9c739ac8cd7d6f0b255ee233c1`.
- Ortak görev başlangıcı: bu belgeyi ekleyen commit. İki dış worktree bu commit'ten oluşturulur; kesin SHA checkpoint manifestinde kaydedilir.
- Codex: `C:\Users\LENAVO\.codex\worktrees\quartz-finalization`, `codex/pyramid-finalization-20261102`.
- Claude: `C:\Users\LENAVO\.codex\worktrees\quartz-final-claude`, `codex/final-claude-services-20261102`.
- Antigravity: `C:\Users\LENAVO\.codex\worktrees\quartz-final-antigravity`, `codex/final-antigravity-lifecycle-20261102`.

Ana kullanıcı checkout'unda branch değiştirme, başka sahibin worktree'sinde yazma veya kurulu EXE'yi ayrı ayrı güncelleme yok. Dış teslimler ortak başlangıca göre commit/patch ve raporla gelir; entegrasyon ve dağıtım Codex'te.

## Dosya sahipliği

| Sahip | Sorumluluk | Yazabileceği üretim dosyaları |
|---|---|---|
| Codex | Görev/run/oturum korelasyonu, görev sırasında ek talimat, doğrulanmış Stop, restart/recovery, tek yazıcı ve son kabul | `core/agent_chat.py`, `core/conversation_store.py`, `core/multi_agent_service.py`, `core/natural_desktop.py`, `core/chat_coordination.py`, `core/task_outcome.py`, `core/run_evidence_store.py`, `core/writer_journal.py`; final package verifier/build kontrolleri |
| Claude | GUI bridge ile uygulama servislerini ayırma; API uyumluluğu, servis sahipliği ve kapanış adaptörü | `gui.py` Api/QuartzUI bölümleri; yeni `core/application_services.py`; yalnız yeni payload'lar gerektirirse `ui/js_chat.py`, `ui/js_desktop.py`, `ui/js_lifecycle.py`; `tests/test_application_composition.py`, `tests/test_gui_service_lifecycle.py` |
| Antigravity | Kooperatif backend/entry kapanışı, lazy service kabul kapısı, tüm sahiplerin temizlenmesi, gerçek süreç çıkış kanıtı | `main.py`, `quartz_entry.py`, gerekirse yeni `core/shutdown.py`; `core/process_tree.py`, `core/codex_runtime.py`, `core/antigravity_runtime.py`, `core/gemini_runtime.py`; `tests/test_cooperative_shutdown.py`, ilgili mevcut runtime/process testleri |

Her ajan kendi raporunu ve yeni ilgili testlerini yazabilir. Ortak `PYRAMID.md`, `TEAM.md`, `scripts/run_safe_tests.py`, paket spec/verify, CI ve diğer sahibin dosyalarında değişiklik için integration request bırak; doğrudan yazma. Mevcut global task motorunu yeniden kurma, yeni genel event/behavior registry yaratma.

## Paylaşılan sözleşme

1. `task_id` mevcut chat `turn_id` referansıdır; provider `run_id` ve session/thread kimliği bundan ayrıdır. Eski kayıtlara zorunlu migration yok.
2. Stop'un yerel yayın/izin fence'i hemen konur. Bu, tüm çocuk süreçlerin çıktığının kanıtı değildir. Bekleyen veya başarısız cleanup yeni yazma/operatör işini başlatmaya izin vermez.
3. Kapanış sonucu tercihen salt JSON receipt: `status` = `confirmed | pending | failed`, `components` = bileşen bazlı sonuçlar, `errors` = hassas veri içermeyen kod/türler. Mevcut GUI/IPC public imzalarının uyumluluğu korunur; yeni receipt alanları eklemelidir.
4. `confirmed` ancak sahip olunan işler/süreçler ve bilinen çocuklar gerçekten durduysa kullanılır. Bilinmeyen durum başarı değildir. Bir cleanup hatası diğer sahiplerin cleanup'ını atlatmaz.
5. Kapanışta yeni servis oluşturulmaz. Normal kapanışta `os._exit`/`SIGTERM` ile cleanup atlanmaz; PID tahminiyle ilgisiz süreç kapatılmaz.
6. Ana sohbet tek görev girişidir. Ek talimat aynı görev/conversation/project ve mevcut yetki kapsamına bağlıdır; yeni scope/operatör yetkisi kendiliğinden doğmaz. Başarısız/iptal edilen görevin kuyruğu gizlice çalışmaz.
7. Kod derlenmesi, mocked test, gerçek CLI smoke ve paketli ana sohbet kabulü ayrı kanıt düzeyleridir.

## Entegrasyon bağımlılıkları

- Claude `Api.cleanup_before_exit` içinde GUI'ye ait scope/işleri bırakır; backend stop isteğini mevcut kimlik doğrulamalı IPC üzerinden iletir. Backend singleton'larının sahibi olmaz.
- Antigravity backend/entry stop ve join akışını sağlar. GUI içini değiştirmez; gerekiyorsa Claude'a çağrı/receipt beklentisini raporlar.
- Codex `AgentChatService.close`/Stop receipt ve late-dispatch yarışını tamamlar. Antigravity, bu dosyayı değiştirmek yerine beklediği close/receipt bağını raporlar.
- Frontend zaten yedi işlevsel JS fragmanına ayrıldı; yeniden monolit veya framework dönüşümü yapılmaz. Yeni sekiz UI modülünün paket verifier kaydı Codex'te.

## Ortak kabul kapıları

- Normal sohbet gereksiz model/tool görevine dönmez; gerçek görev mevcut checkpoint/tek writer akışına girer.
- Aynı sohbetten ek talimat, Stop, geç provider dönüşü ve yeniden başlatma; yanlış conversation'a yayın veya çift yürütme yok.
- Birlikte modunda roller/mesaj kimlikleri doğru; fare/klavye tek operatörde.
- GUI kapanışı, backend IPC shutdown, hata sırasında cleanup, tekrar shutdown ve kapanış sırasında dispatch yarışları testlidir.
- Kaynak testleri, tam safe suite, paket denetimi, gerçek Codex/Google smoke ve mümkün olan paketli ana sohbet kabulü; skip/BLOCKED açık raporlanır.
- Q teması, reduced motion, model tercihleri, onboarding, geçmiş ve uygulama erişim güvenlikleri korunur.
- Kullanıcı verisi diff kontrolü, runtime-owned process kalıntısı denetimi ve geri alma checkpoint'i vardır.

## Kapsam dışı / korunacaklar

ASTER ve `C:\WarbandIsland`, kullanıcı kayıtları, Notion üçüncü ajan/Worker, yeni UI tasarımı, yeni WSE2/runtime ve kamuya yayın bu görevin dışında. Notion ortak hafıza olarak kalır. Tek `full` kullanıcı tercihi korunur; broker kapsamı, native onay, UAC, Stop ve taze gözlem kontrolleri kaldırılmaz. `.env`, token, cookie, özel geçmiş veya kullanıcı verisi delivery/bundle içeriğine eklenmez. Secret depolama/onboarding sağlayıcı migration'ı bu sahiplik diliminde kendiliğinden açılmaz; somut bulgu varsa raporlanır.

## Teslim standardı

Her teslim: ortak SHA, commit SHA, dosya listesi, yeniden üretim/gerçek kusur, yapılan dar düzeltme, test komutu ve sonucu, skip, SOURCE/BUILT/LIVE ayrımı, bilinen açıklar ve geri alma. Dış ajan bağımsız EXE dağıtmaz, diğer ajanın işini tamamlandı saymaz ve yeni public push yapmaz.
