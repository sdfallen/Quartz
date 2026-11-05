# Quartz Dalga 2 — Sağlamlaştırma, Ölçüm ve Çapraz İnceleme Raporu (5 Kasım 2026)

- **Dal:** `antigravity/wave0-wave1-analysis-20261105`
- **Worktree:** `C:\Users\LENAVO\.gemini\antigravity\worktrees\quartz-wave0-wave1-20261105`
- **Temel (`main`):** `1a18556` (`c13ff65` birleştirme commit'i)

---

## 1. P0-3 Çalışma Zamanı (Runtime) Oracle Alanları (`b26786e`)

`core/codex_runtime.py` ve `core/antigravity_runtime.py` içine, çalışma zamanının kendi son başarı kararını (`status`) değiştirmeden, Codex'in görev oracle'ında kullanacağı yapılandırılmış çalışma zamanı olay alanları eklendi.

### Eklenen Alan Adları (`run` kaydı ve `get(run_id)` çıktısı)

| Alan Adı | Tür | Açıklama |
|---|---|---|
| `command_results` | `list[dict]` | Çalıştırılan her iç komutun sıralı kaydı: `{"seq": int, "tool": str, "command": str, "exit_code": int \| None, "ok": bool, "state": "DONE" \| "ERROR", "output": str, "error": str}` |
| `command_exit_codes` | `list[int \| None]` | İç komutların çalıştırılma sırasına göre çıkış kodları listesi (örn. hata → onarım → başarılı test akışında `[1, 0]`). |
| `file_changes` | `list[dict]` | Bildirilen her dosya değişikliği olayı: `{"seq": int, "path": str, "kind": "add" \| "write" \| "update" \| "delete", "tool": str, "state": "DONE" \| "ERROR"}` |
| `error_events` | `list[dict]` | Çalışma sırasında oluşan tüm hata olayları (iç komut sıfır-dışı çıkışları dahil): `{"seq": int, "source": str, "kind": str, "tool": str \| None, "command": str \| None, "exit_code": int \| None, "message": str}` |

> [!NOTE]
> `seq` alanı aynı koşu (`run_id`) içindeki `command_results`, `file_changes` ve `error_events` kayıtları arasında ortak monotonik sıra numarasıdır. Böylece oracle, `seq=1` (`exit_code=1`) hatasından sonra `seq=2` (`edit_file`) ve `seq=3` (`exit_code=0`) onarım zincirini kesin sırayla doğrulayabilir.

### Codex Oracle İçin Örnek Kayıt (Hata → Düzenleme → Başarılı Test)

```json
{
  "id": "example_run_id",
  "status": "completed",
  "command_exit_codes": [1, 0],
  "command_results": [
    {
      "seq": 1,
      "tool": "command_execution",
      "command": "pytest -q",
      "exit_code": 1,
      "ok": false,
      "state": "ERROR",
      "output": "1 failed",
      "error": "1 failed"
    },
    {
      "seq": 3,
      "tool": "command_execution",
      "command": "pytest -q",
      "exit_code": 0,
      "ok": true,
      "state": "DONE",
      "output": "1 passed",
      "error": ""
    }
  ],
  "file_changes": [
    {
      "seq": 2,
      "path": "calc.py",
      "kind": "update",
      "tool": "file_change",
      "state": "DONE"
    }
  ],
  "error_events": [
    {
      "seq": 1,
      "source": "command",
      "kind": "nonzero_exit",
      "tool": "command_execution",
      "command": "pytest -q",
      "exit_code": 1,
      "message": "1 failed"
    }
  ]
}
```

---

## 2. Çökme Sonrası Süreç Ağacı Temizliği (`exam-long-02`, Commit `01c115a`)

### Düzeltme Öncesi Sahte Süreç Ölçümü

`Quartz.exe`'yi simüle eden üst süreç (`quartz_sim`), `CodexRuntime` ve `AntigravityRuntime` üzerinden `cmd.exe -> node.exe -> grandchild node.exe` süreç ağacı başlattıktan sonra `TerminateProcess` (`quartz_sim.kill()`) ile aniden sonlandırıldı:
- **Düzeltme öncesi sonuç:** `After abrupt Quartz.exe kill: cli_alive=True, grandchild_alive=True` — üst süreç aniden öldüğünde `stop_process_tree()` hiç çalışmadığı için alt ve torun süreçler yetim (orphan) olarak hayatta kaldı.

### Uygulanan Düzeltme (`core/process_tree.py`, `core/codex_runtime.py`, `core/antigravity_runtime.py`)

- `core/process_tree.py` içine Windows Job Object (`CreateJobObjectW` + `SetInformationJobObject` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000`) bağlayan `bind_kill_on_close_job(process)`, `sync_process_job(process)`, `wait_process_with_job_sync(process, timeout)` ve `close_process_job(process)` eklendi.
- `CodexRuntime.start()` / `_wait()` ve `AntigravityRuntime.start()` / `_wait()` başlatılan CLI sürecini ve alt süreç ağacını bu Job Object'e bağlayacak şekilde güncellendi. `Quartz.exe` aniden çökerse veya `TerminateProcess` ile kapatılırsa işletim sistemi son Job handle'ı kapandığı anda tüm `cmd.exe`/`codex.exe`/`agy.exe`/`node.exe` alt ağacını otomatik olarak sonlandırır.

### Düzeltme Sonrası Ölçüm Çıktısı

```text
[codex] Spawned tree under simulated Quartz.exe (pid=12304): cli=19816, node=15440, grandchild=22108
[codex] After abrupt Quartz.exe kill (AFTER FIX): cli_alive=False, node_alive=False, grandchild_alive=False
[agy] Spawned tree under simulated Quartz.exe (pid=18092): cli=21604, node=10884, grandchild=19420
[agy] After abrupt Quartz.exe kill (AFTER FIX): cli_alive=False, node_alive=False, grandchild_alive=False
```

### Entegrasyon İsteği (`IR-AGY-CRASH-JOB-02`)

- **Hedef dosya:** `core/desktop_native.py` / `core/desktop_agents.py` (Sahibi: Claude, İnceleyen: Codex)
- **Neden:** `QuartzDesktopMCP.exe` yan süreci başlatılırken `bind_kill_on_close_job(process)` çağrılmadığı için `Quartz.exe` çöktüğünde yetim `QuartzDesktopMCP.exe` süreçleri kalabilmektedir.
- **Öneri:** `subprocess.Popen` ile `QuartzDesktopMCP.exe` başlatıldıktan hemen sonra `from core.process_tree import bind_kill_on_close_job; bind_kill_on_close_job(proc)` çağrılması.

---

## 3. P1-3 Salt Okunur Antigravity İnceleme Sınırının Gerçek Ölçümü ve Koruması (`fd1a71e`)

### İzole Klasörde Canlı Ölçüm Bulguları

İzole geçici klasörde (`tempfile.TemporaryDirectory`), `AntigravityRuntime.start(..., write=False, full_access=False, model="gemini-3.8-flash-low", effort="low")` ile iki ayrı canlı sınır testi yapıldı:

1. **Kabuk komutu (`run_command`) denemesi (`--mode plan --sandbox`):**
   - `agy.exe` headless izin politikası `run_command` aracını otomatik reddetti:
     - `Denied actions: [{'action': 'command', 'display_name': 'RunCommand'}]`
     - `Status: failed`
     - Diskteki dosyalar değişmedi (`existing.txt: 'original\n'`).
2. **Yerleşik dosya yazma araçları (`write_file` / `edit_file`) denemesi (`tool_guard=False` -> `--mode plan --sandbox` ve `tool_guard=True` -> `--mode auto --sandbox`):**
   - **Kritik Bulgu (LIVE VERIFIED):** Windows'ta `agy.exe --mode plan --sandbox` (ve `warning: --mode auto is not available because the terminal sandbox is not available on this host` uyarısıyla varsayılan moda düşen `--mode auto --sandbox`), kabuk komutlarını engellediği halde **yerleşik `write_file` ve `edit_file` araçlarının çalışma dizinine (`project_path`) dosya yazmasını ENGELLEMEMEKTEDİR.**
   - Canlı koşuda `agy.exe`, `readonly_probe.txt` dosyasını oluşturdu ve `existing.txt` dosyasını değiştirdi; ayrıca `stream-json` çıktısında bu araçları `state: "DONE"` olarak bildirdi (`files_changed` ve `file_changes` doldu).
   - Düzeltme öncesinde `AntigravityRuntime._wait`, `denied_actions` boş olduğu için bu salt okunur koşuyu **`status: "completed"`** olarak döndürüyordu.

### Uygulanan Çalışma Zamanı Koruması (`core/antigravity_runtime.py`, `core/codex_runtime.py`)

Yeni izin vermeden ve eşzamanlı izinli bir yazıcının (`writer`) disk değişikliklerini okuyucuya (`reader`) mal etmeden:
- Yalnız salt okunur (`sandbox in {"sandbox", "read-only"}`) koşunun **kendi olay akışında** (`_read_stdout`) tamamlanan bir dosya değiştirme aracı (`write_file`, `edit_file`, `file_change` vb.) görüldüğünde:
  - `record["unauthorized_write_detected"] = True`
  - `record["unauthorized_files_changed"]` listesine ilgili dosya yolu eklenir.
  - `record["error_events"]` içine `kind="unauthorized_readonly_write"`, `source="sandbox_guard"` kaydı düşülür.
  - `AntigravityRuntime` içinde `record["denied_actions"]` listesine `{"action": "write", "display_name": tool_name, "path": path, "reason": "read_only_violation"}` eklenir.
  - `_wait()` sonunda koşu kesin olarak **`status = "failed"`** yapılır (`completed` olamaz).
- Eşzamanlı başka bir yazıcı aynı proje klasöründe dosya değiştirdiğinde, salt okunur koşunun kendi `stream-json` akışında yazma aracı olayı bulunmadığından okuyucu yanlışlıkla suçlanmaz (`test_p1_3_readonly_run_does_not_blame_reader_for_concurrent_writer_disk_changes` ile doğrulandı).

---

## 4. `exam-code-06` Gizli Sınav Varyantları (Holdout Özeti)

Claude'un görev listesindeki `exam-code-06` görevi için 10 adet kasıtlı hatalı diff varyantı **repo dışında** `C:\Users\LENAVO\.gemini\quartz-exam-holdout\` dizininde hazırlandı. Repo içine hiçbir diff içeriği, hedef dosya adı veya hata açıklaması yazılmamıştır.

- **Hazırlanan gizli varyant adedi:** `10`
- **Holdout Manifest SHA-256 (`manifest.json`):** `e01c2b83064a5d12da48dff3db6a6441461c032d5c9f3f8f4229568346a26491`

| Varyant Kimliği | Dosya Adı (Repo Dışı) | SHA-256 Özeti |
|---|---|---|
| `exam-code-06-v01` | `variant_01.diff` | `23ab1c4d7d2b1916a6c107449bb4514b2dd2289535cb87bdc962b8ec8fb10152` |
| `exam-code-06-v02` | `variant_02.diff` | `a3751c0a8c3e795738fa0fbf42d400aacbaf8268d44d4bb97aface074caa42ed` |
| `exam-code-06-v03` | `variant_03.diff` | `be7533956024e341fe0a2840dcb50f04c519ccb2a967dee87aebdf55c1ce8938` |
| `exam-code-06-v04` | `variant_04.diff` | `d3bebf94f1413354193e3f89df19ba986f35165510821c23d57fc5ad1c3864cd` |
| `exam-code-06-v05` | `variant_05.diff` | `33356b49776306b5fc07bbe91303a176c7694817300107813460bfed48ac5c22` |
| `exam-code-06-v06` | `variant_06.diff` | `9e523881d4b99e5c39fe0dd215dbf76450b042dcf73043e21bb12e7226402e8c` |
| `exam-code-06-v07` | `variant_07.diff` | `fee49ebb8e41c18ae37e3ffb8bcb1b24a4034de1d05d4696a034b309072b3ce4` |
| `exam-code-06-v08` | `variant_08.diff` | `e6e85c8df8a1a22423251018294badc31f02c29b14f22b6362906fa0cc504539` |
| `exam-code-06-v09` | `variant_09.diff` | `d66b5e76b356a1e1a3b12cb2a193f0e47392d337a36665e6535f4bb1097571c5` |
| `exam-code-06-v10` | `variant_10.diff` | `16533265784d174ca68a803c81e39e12bd7384052527dae164efebe7a4fe26a7` |

---

## 5. Codex Dalga 2 Değişikliklerinin Bağımsız İncelemesi

İncelenen Codex commit'leri (`C:\Users\LENAVO\.codex\worktrees\quartz-wave2-20261105`):
- `577c264` (`codex/wave2-step1-20261105`): `fix(exam): reject empty or spoofed runs and contain normal-exit descendants`
- `e6cc681` (`codex/wave2-step2-20261105`): `fix(outcomes): distinguish execution evidence and partial group results`
- `8aa5278` (`codex/wave2-step3-20261105`): `fix(intent): honor withdrawals and general Turkish desktop directives`
- `99e82d0` (`codex/wave2-step4-20261105`): `perf(squad): cache idle display snapshots with WAL invalidation`
- `7ea2ac4` (`codex/wave2-step5-20261105`): `feat(oracle): verify host-declared task postconditions independently`

### 5.1 Bağımsız Test Çalıştırma Çıktısı

Komut:
```text
python -X utf8 -B scripts/run_safe_tests.py tests.test_exam_process tests.test_task_exam_runner tests.test_wave2_outcomes tests.test_wave2_intent_corpus tests.test_squad_idle_cache tests.test_task_oracle
```

Gerçek çıktı:
```text
...........................................................
----------------------------------------------------------------------
Ran 59 tests in 5.437s

OK
```

### 5.2 Doğrulanan İyileştirmeler

1. **Dalga 1 Bulgularının Kapatılması (`577c264`):**
   - `scripts/task_exam_runner.py:70-76`: `verdict('unittest', ...)` artık `stdout` yerine `stderr` özetini satır sonu çapasıyla (`^Ran (\d+) tests? in [^\n]+\n\s*OK(?: \(skipped=(\d+)\))?\s*$`) kontrol ediyor ve `int(match[1]) <= int(match[2] or 0)` olduğunda `NOT VERIFIED` döndürüyor (Dalga 1 Bulgu B1 kapandı).
   - `scripts/exam_process.py:25-79` ve `scripts/task_exam_runner.py:100-155`: Görev süreçleri `CREATE_SUSPENDED` (`0x4`) ile başlatılıp `_WindowsJob`'a atanıyor; normal çıkışta (`exit_code == 0`) bile `self.job.empty()` kontrol edilerek arkada torun süreç kaldıysa `status = 'BLOCKED'` işaretleniyor (Dalga 1 Bulgu B3 kapandı).
2. **Sonuç Sözleşmesi ve Bağımsız Oracle (`e6cc681`, `7ea2ac4`):**
   - `core/task_outcome.py:4-24` ve `core/task_oracle.py:18-108`: Modelin metin çıktısı veya `exit_code == 0` tek başına `goal_verdict = 'VERIFIED'` üretemiyor; yalnızca `_SEAL` ile mühürlenmiş host `GoalEvaluation` nesnesi (`HOST POSTCONDITION`) `status == 'completed'` ve `source_validation != 'FAILED'` iken `goal_verdict = 'VERIFIED'` yapabiliyor.
   - `core/task_oracle.py:36-50`: Symlink ve Windows junction/reparse point (`st_file_attributes & 0x400`) kaçışları reddediliyor; okuma öncesi ve sonrası `(st_ino, st_size, st_mtime_ns)` karşılaştırılarak eşzamanlı değişen dosyalar reddediliyor.
3. **Squad Boşta Önbellekleme (`99e82d0`):**
   - `core/multi_agent_service.py:267-315`: Başlatılmış (`.squad/messages.db` mevcut) projelerde boşta durumda `messages.db` ve `messages.db-wal` `(st_ino, st_size, st_mtime_ns)` imzası değişmedikçe 300 saniye boyunca Squad görüntüsü derin kopya (`copy.deepcopy`) ile önbellekten dönüyor; aktif görev varken önbellek devre dışı bırakılıyor.

### 5.3 Tespit Edilen Bulgular (`dosya:satır`)

#### Bulgu C-W2-1 (Yüksek — "Doğrulanmamış iş başarı görünmeyecek" boşluğu): Grup sohbeti 2. tur (`_run_mutual_evaluation_round`) ve tartışmaya devam (`_run_continue_discussion_turn`) hataları yutup turu `completed` bitiriyor
- **Konum:** `core/agent_chat.py:1747-1768`, `core/agent_chat.py:1874-1915`, `core/agent_chat.py:1939-1954`
- **Kanıt (SOURCE):**
  - `_run_mutual_evaluation_round` (`core/agent_chat.py:1874-1915`) içinde `run_codex_eval()` ve `run_agy_eval()` alt iş parçacıkları `except Exception as exc:` bloğunda balon durumunu `"failed"` olarak güncelliyor (`codex_r2_meta.update({"status": "failed", ...})`), ancak çağıran fonksiyona hiçbir başarı/başarısızlık durumu döndürmüyor (`return None`).
  - Bunun sonucunda:
    1. `_run_collaboration_turn` (`core/agent_chat.py:1747-1768`) içinde `rounds >= 2` olduğunda 1. tur başarılı (`codex_r1_ok=True, agy_r1_ok=True`) geçip 2. turda ajanlardan biri veya her ikisi hata verse bile, 1765–1768. satırlar yalnızca 1. turun değişkenlerine (`codex_r1_ok`, `agy_r1_ok`) bakarak `participants = {'codex': 'completed', 'antigravity': 'completed'}` yazıyor ve turu **`"completed"`** olarak kapatıyor.
    2. `_run_continue_discussion_turn` (`core/agent_chat.py:1939-1954`) ise `_run_mutual_evaluation_round(...)` çağrısından hemen sonra 1954. satırda koşulsuz olarak `self._finish_turn(first_msg_id, "completed")` çağırıyor; 2. turda her iki ajan da kota veya bağlantı hatasıyla çökmüş olsa bile tur durumu `"completed"` oluyor.
- **Öneri:** `_run_mutual_evaluation_round` fonksiyonu `{"codex": "completed" | "failed", "antigravity": "completed" | "failed"}` sözlüğü döndürmeli; `_run_collaboration_turn` ve `_run_continue_discussion_turn` son tur durumunu `group_execution_status(...)` ile birleştirerek `"completed"`, `"partial"` veya `"failed"` kararına bağlamalıdır.

#### Bulgu C-W2-2 (Orta — Mesaj projeksiyonunda `participants` kaybı): `_enrich_messages` kısmi grup sonucunu mesajların `outcome` alanına taşımıyor
- **Konum:** `core/agent_chat.py:766-776` ve `core/agent_chat.py:856-860`
- **Kanıt (SOURCE):**
  - `poll_turn()` (`core/agent_chat.py:741-742`) aktif/son tur için `execution_outcome(turn.get('status','unknown'), participants=turn.get('participant_statuses'))` hesaplıyor.
  - Ancak `_finalize_assistant_message` (`core/agent_chat.py:857`) ve `_enrich_messages` (`core/agent_chat.py:772-776`) `execution_outcome(...)` çağrısına `participants` parametresini geçirmiyor. Birlikte modunda Codex başarılı, Antigravity başarısız olduğunda, Codex mesaj balonunun kendi `status` alanı `"completed"` olduğu için `_enrich_messages` bu mesajın `metadata['outcome']` alanında `execution_status: "completed"` ve `participants: {}` üretiyor.

#### Bulgu C-W2-3 (Orta — Squad önbellekleme kenar durumu): `.squad/messages.db` henüz oluşmamış (başlatılmamış) projelerde boşta `squad.exe --version` alt süreci çalışmaya devam ediyor
- **Konum:** `core/multi_agent_service.py:268-315` ve `core/squad_adapter.py:70-89`
- **Kanıt (SOURCE):**
  - `_squad_signature(project)` (`core/multi_agent_service.py:272`) `.squad/messages.db` dosyası yoksa `None` döndürüyor.
  - `_squad_snapshot(self, project, squad)` (`core/multi_agent_service.py:297, 312`) yalnızca `signature is not None and not error` olduğunda önbellek okuyor ve yazıyor.
  - `.squad/messages.db` olmayan bir projede her `status()` çağrısında `squad.status()` (`squad.exe --version` alt süreci) çalıştırılıyor, ardından `squad.agents()` `SquadCommandError("Squad workspace is not initialized...")` fırlattığı için `error` dolu kalıyor ve sonuç önbelleğe alınmıyor. Dolayısıyla Squad başlatılmamış projelerde her 15 saniyede bir `squad.exe --version` (10 dakikada ~40 alt süreç) açılmaya devam ediyor.
- **Öneri:** `not squad.initialized` durumunda `squad.agents()`/`tasks()`/`history()` hiç çağrılmamalı ve `('.squad_uninitialized', (root / 'messages.db').exists())` imzasıyla boşta önbelleğe alınmalıdır.

#### Bulgu C-W2-4 (Düşük/Orta — `TaskOracle` Windows CRLF duyarlılığı ve kayıt yarış penceresi)
- **Konum:** `core/task_oracle.py:102-104` ve `core/multi_agent_service.py:90-99`
- **Kanıt (SOURCE):**
  - `core/task_oracle.py:104`: `mode == 'text'` kontrolü `data == expected.encode('utf-8')` ile ham bayt eşitliği yapıyor. Windows'ta ajan veya standart Python metin yazımı `\r\n` ürettiğinde, çok satırlı `expected` metni `\n` içeriyorsa içerik birebir doğru olduğu halde `FAILED` döner (`sha256` tam bayt içindir, `text` modunda `\r\n` -> `\n` normalizasyonu veya açık seçenek güvenli olur).
  - `core/multi_agent_service.py:97`: `register_goal_oracle` `runtime.get(run_id).get('status') != 'running'` kontrolü yapıyor; `dispatch_*` arka plan iş parçacığını başlattıktan sonra döndüğü için çok hızlı tamamlanan koşularda `register_goal_oracle` çağrılmadan önce durum `'completed'` olabilir. Oracle planının doğrudan `dispatch(..., goal_checks=...)` içinde süreç başlamadan önce kaydedilmesi bu yarış penceresini kapatır.
