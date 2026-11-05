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
