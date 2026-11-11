# Claude — servis ve arayüz sınırı: kapanış raporu

Tarih: 2026-11-02. Sahip: Claude.

- Ortak başlangıç: `2c57a49c5e0db7cfe1174b68a1508690d97035e6`
  (`codex/final-claude-services-20261102`, worktree `quartz-final-claude`).
  Tree `5bda0ae`, kullanıcının worktree index'iyle `git write-tree` üzerinden
  eşleşti.
- Bu teslim: `claude/final-services` dalında tek commit (SHA teslim mesajında).
- Codex'in agent_chat WIP checkpoint'i alınmadı.

Kanıt seviyesi: **SOURCE + TESTED (Linux, mock/fake bileşenler)**.
BUILT ve LIVE VERIFIED **yok**. Paket kurulmadı, Windows'ta açılmadı, kurulu
EXE'ye ve kullanıcı verisine dokunulmadı. Linux sonucu Windows canlı kabulü değildir.

## 1. Gerçek kusur (baseline'da yeniden üretildi)

`gui.Api.cleanup_before_exit` bileşenleri ardışık kapatıyordu ve aradaki
çağrılar korumasızdı. Baseline `2c57a49` üzerinde bir Python betiğiyle
yeniden üretildi:

```
api._natural.stop -> RuntimeError
sonuç: closing handler RuntimeError fırlattı;
coordination.stop çağrılmadı, desktop.close çağrılmadı, ipc "shutdown" gönderilmedi
```

Ek bulgular (kaynak):
- Kapanış başladıktan sonra bile `_desktop_service()`, `_coordination_service()`,
  `_voice` ve picker akışları yeni bileşen kurabiliyordu. Kapanış çiti yoktu.
- `ipc_send("shutdown")` sonucu okunmuyordu. Hata da başarı gibi `True` dönüyordu.
- Bileşen kurulumu ve sahipliği `Api` içinde dağınıktı: 7 lazy import, 4 kilit ve
  özniteliklerdeki durum.

## 2. Yapılan değişiklik

| Dosya | Değişiklik |
|---|---|
| `core/application_services.py` (yeni, ~300 satır) | `ApplicationServices` + `ServiceFactories`. Lazy, tek örnekli slotlar; kapanış çiti; bileşen bazlı bağımsız kapanış ve doğrulama; idempotent `shutdown()` receipt'i. GUI, `webview` ve IPC import etmez |
| `gui.py` (yalnız `Api`) | Bileşen kurulumu ve sahipliği kompozisyona devredildi. `cleanup_before_exit` receipt üretiyor. Backend shutdown sonucu yorumlanıyor. Kapanıştan sonra picker açılmıyor ve housekeeping thread'i başlamıyor |
| `tests/test_application_composition.py` (yeni) | 17 test |
| `tests/test_gui_service_lifecycle.py` (yeni) | 20 test |

Sorumluluk ayrımı:

| Sorumluluk | Önce | Sonra |
|---|---|---|
| Bileşen kurulumu (Desktop, Natural, Coordination, ArtifactDiagnostics, PackageRepair, Onboarding, Voice) | `Api` metotları içinde lazy import + `self._x = Class()` | `ServiceFactories` (enjekte edilebilir, varsayılanlar lazy import) |
| Tek örnek / yeniden kullanım | `Api` başına ayrı kilitler | `ApplicationServices._get` tek RLock altında |
| İstek başı değişim | `Api` | `start_natural`, `replace_artifact_diagnostics`, `new_repair`/`discard_repair` |
| Kapanış | `Api.cleanup_before_exit` (ardışık) | `ApplicationServices.shutdown()` (çit + bağımsız + doğrulamalı) |
| Native picker / onay | `Api` | `Api` (değişmedi) |
| Backend IPC (auth'lu `ipc_send`) | `Api` | `Api` (değişmedi) |
| Sohbet günlüğü emit'i | `Api` içinde iki kopya | `Api._chat_log_emitter(mesaj)`. Hata metinleri aynı |

Kasıtlı olarak **korunan** özel güvenlik kontrolleri:
- Writer-recovery admission guard, desktop servisi ilk kez döndürülmeden önce
  `broker.admission_guard`'a bağlanıyor. Test ve mutasyonla kanıtlandı.
- Diagnostics yalnız native `.exe` picker'ın verdiği yolla kuruluyor. Önceki
  inceleme önce kapatılıyor.
- `natural_start`'taki tüm önkoşullar aynı sırayla `Api`'de kaldı: sohbet durumu,
  sohbet kimliği, proje, "Başka bir görev/operatör sürüyor", ajan öneki, bağlam
  kırpma, `requested_permission_level`.
- `desktop_task_stop` generation kontrolü, `coordination_stop` plan kontrolü,
  `desktop_operator_start` ikinci operatör yasağı, tek `full` tercihi değişmedi.

Değişmeyenler:
- `gui._HTML` SHA-256 `db61e6fb…95bd02` (önce ve sonra aynı). JS, Q teması,
  reduced motion ve model tercihleri (backend'de, sohbet başına) etkilenmedi.
- Public bridge adları ve payload'ları korundu (`BASELINE_API` testi). `Api()`
  argümansız çağrılabiliyor.
- Eski özel öznitelikler (`_natural`, `_desktop_agents`, …) kompozisyona
  okuma/atama yapan uyumluluk property'leri olarak duruyor. Okuma hiçbir
  zaman bileşen kurmaz. Kapanıştan sonra atama reddedilir.

## 3. Kapanış receipt'i

`Api._shutdown_receipt`, ortak sözleşmedeki biçimi izler:

```json
{"status": "confirmed|pending|failed",
 "components": {"artifact_diagnostics": "...", "natural": "...", "coordination": "...",
                "desktop": "...", "voice": "...", "repair": "...", "onboarding": "...",
                "backend": "..."},
 "errors": [{"component": "natural", "code": "close_failed", "type": "RuntimeError"}]}
```

Bileşen başına `confirmed` ölçütü (kendi durumundan doğrulanır, bilinmeyen başarı değildir):

| Bileşen | Kapanış | `confirmed` ancak | Aksi |
|---|---|---|---|
| artifact_diagnostics | `shutdown()` | hiçbir inceleme thread'i yaşamıyorsa | pending |
| natural | `stop()` | `status().active` false ve `job.cleanup.status` `completed` ise | cleanup `failed` → failed. `running`/aktif → pending |
| coordination | `stop()` | `status().active` false ise | pending |
| desktop | `close()` | broker oturumu aktif değilse | pending |
| voice | `stop_wake_loop()` + `stop_speaking()` | `wake_active` false ise | pending |
| repair | plan bırakılır | diagnostics kilidi 2 sn içinde alınabildiyse (apply sürmüyorsa) | pending, plan korunur |
| onboarding | **kapatılmaz** | kurulum/giriş penceresi sürmüyorsa | pending (kullanıcının giriş penceresi öldürülmez) |
| backend | auth'lu `ipc_send("shutdown")` | backend `data.status` olarak receipt döndürürse ona uyulur | `ok` ama receipt yoksa pending. IPC hatası/exception → failed |

Diğer kurallar:
- Hata kayıtları yalnız bileşen, kod ve exception tür adı taşır. Mesaj metni,
  yol veya IPC hata metni girmez (test edildi).
- Tekrar `cleanup_before_exit`: confirmed bileşen yeniden kapatılmaz,
  failed/pending olan yeniden denenir. Backend bir kez kabul ettiyse
  (pending/confirmed) `shutdown` tekrar gönderilmez, failed ise yeniden denenir.
- Kompozisyonun kendisi çökse bile backend shutdown istenir ve receipt `failed` olur.
- Pencere kapanması eskisi gibi daima `True` ile serbest bırakılır.

## 4. Testler (bu ortamda gerçekten koşulan)

Komutlar repo kökünde, Linux, Python 3.13, Node. Loglar teslim paketinde (`logs/`).

| Komut | Sonuç |
|---|---|
| `python -B scripts/check_python_syntax.py` | 250 dosya OK |
| `python -B scripts/check_gui_javascript.py` | exit 0 |
| `python -B scripts/run_safe_tests.py` + 17 modül (iki yeni dosya, frontend boundary/theme/polling/keyboard/compact, notion_tools_ui, pyramid_integration_review, desktop_task_ui, chat_coordination, permission_selection, diagnostics_expansion, desktop_agents, conversation_delete, chat_task_entry, notion_frontend_integration) | 202 test OK, 12 skip |
| `python -B scripts/run_safe_tests.py` (tam) | Sonra: 879 test. Baseline `2c57a49`: 842 test. İkisinde de aynı 2 fail + 19 error, 17 skip |
| `python -B scripts/audit_publish.py --staged --history` | PASS, 0 bulgu |
| `git diff --cached --check` | Temiz |

Hedefli koşudaki 12 skip, "Integration requires the built observer guard helper"
nedeniyle; Windows yardımcı programı gerekiyor.

Tam suite: başarısız ve hatalı test kimlik listeleri baseline ile `diff` ile
birebir aynı. Hepsi Linux ortamından kaynaklanıyor: `pyautogui` gibi Windows
modülleri eksik, `codex.cmd`/`node.exe` yolları, UAC/native testleri. +37 test
bu teslimin yeni testleri.

Mutasyon kontrolleri (geçici, geri alındı):

| Mutasyon | Sonuç |
|---|---|
| Kapanışta exception yutmayı kaldırma (eski ardışık davranış) | 4 test düştü |
| Kapanış çitini devre dışı bırakma | 2 test düştü |
| Admission guard bağlamayı silme | 2 test düştü |

Yeni testlerin kanıtladıkları:
- Lazy kurulum, aynı örneğin yeniden kullanımı, 8 thread'li eşzamanlı ilk
  kullanımda tek kurulum.
- Kapanış sırasında ve sonrasında yeni örnek yasağı. Kapanışla yarışan bir
  factory'nin ürettiği örnek de kapatılıyor, sızmıyor.
- Tek hatada diğer tüm bileşenler ve backend kapanıyor.
- Tekrar cleanup (idempotent + yalnız hatalıları yeniden deneme).
- Doğrulanamayan durum pending kalıyor.
- Kapanıştan sonra bridge çağrıları hata dönüyor: picker açılmıyor, sohbete
  yazılmıyor, hiçbir şey kurulmuyor.
- Kompozisyon modülü GUI/webview/IPC import etmiyor. `Api` artık bileşen
  sınıflarını import/inşa etmiyor (AST).

## 5. Integration request'ler

**IR-A — Antigravity (`main.py` `shutdown` action): receipt döndür.**
- Bugün `{"status":"ok","data":"Shutting down"}` dönüyor, ardından 0,5 sn sonra
  `os.kill(SIGTERM)` çalışıyor. GUI bunu doğru biçimde `backend: pending` olarak
  kaydediyor.
- Öneri: `data = {"status": "confirmed|pending|failed", "components": {...},
  "errors": [...]}`. `confirmed` yalnız kooperatif stop/join bittiyse kullanılsın.
  SIGTERM ile cleanup atlanmasın (ortak sözleşme madde 5).
- Çağrı noktası: `gui.Api._request_backend_shutdown`.
- Test: `test_backend_receipt_is_respected` GUI tarafını zaten kapsıyor.
  Antigravity tarafında `tests/test_cooperative_shutdown.py` ile eşlenmeli.

**IR-B — Codex (paket):** `Quartz.spec` hiddenimports ve
`scripts/verify_desktop_package.py` modül listesine `core.application_services`
eklenmeli. Modül `gui`'nin üst seviye statik import'u olduğu için PyInstaller
analizi bulur, ama verifier listesi açıkça kontrol etmeli. Ardından build ve
EXE'nin izole bir kopyasıyla açma–kapama kontrolü yapılmalı.

**IR-C — Codex (`core/chat_coordination.py`, isteğe bağlı):** `stop()` bir
cleanup raporu döndürmüyor. GUI yalnız `active` alanına bakabiliyor.
`NaturalDesktopTask.job["cleanup"]` biçiminde bir rapor olursa receipt aynı
derinlikte doğrulanır.

**IR-D — Codex (son kabul):** Kapanış süresi. Bileşen join'leri, closing handler
içinde ardışık çalışıyor: coordination 5 sn, diagnostics thread başına 6 sn,
repair kilidi 2 sn. Bu davranış önceden de vardı; repair beklemesi bu teslimle
eklendi. Paketli kabulde pencere kapanma süresi ölçülmeli.

## 6. Gerçek kalan açıklar

- BUILT/LIVE yok. Windows'ta pywebview `closing` olayının bu handler ile
  gerçekten kapanması, paketli GUI'de ölçülmedi.
- `_shutdown_receipt` yalnız bellekte. Kapanan pencerede kullanıcıya veya
  kalıcı loga yazılmıyor. Nereye yazılacağı (backend kapanırken) Codex ve
  Antigravity'nin kapanış kaydı kararına bağlı.
- `coordination_route` içindeki niyet yönlendirmesi (136 satır) hâlâ `Api`'de.
  Bu teslim sahiplik ve kapanışı ayırdı, yönlendirme kurallarını taşımadı.
  Taşımak davranış riski taşıyor ve görev/oturum sözleşmesi Codex'te.
- Onboarding'in sürmekte olan kurulum/giriş işi kapanışta durdurulmuyor, yalnız
  `pending` raporlanıyor. Bunu öldürmek yeni bir semantik olurdu, yapılmadı.
- Linux'ta 21 baseline hatası Windows bağımlılıklarından kaynaklanıyor ve bu
  teslimle değişmiyor.

## 7. Geri alma

Tek commit. Veri, şema veya kullanıcı dosyası değişikliği yok:
```
git revert <commit>
```
Ya da `core/application_services.py`'yi ve iki yeni test dosyasını sil,
`gui.py`'yi `2c57a49` sürümüne döndür (`git checkout 2c57a49 -- gui.py`).
Bridge adları değişmediği için JS tarafında geri alma gerekmez.
