# Quartz Sistem Piramidi — Provider/Runtime ve Süreç Katmanı Raporu

**Tarih:** 2026-11-01  
**Sorumlu Model / Rol:** Antigravity 3.8 Flash High (Provider / Runtime ve Süreç Katmanı Sahibi)  
**Koordinatör:** Codex  
**Temel Baseline:** `047fa6e` (`codex/architecture-pyramid-20261101`)  
**Çalışma Dalı (Branch):** `antigravity/pyramid-runtime-20261101`  
**Çalışma Ağacı (Worktree):** `C:\Users\LENAVO\.gemini\antigravity\worktrees\quartz-pyramid-runtime`  

---

## 1. Piramit Seviyesi ve Sorumluluk Sınırları

Quartz mimari piramidinde (`docs/architecture/PYRAMID.md`) Antigravity alanı:
- **Katman 3 (Sağlayıcı ve Yetenek Adaptörleri):** `core/codex_runtime.py`, `core/antigravity_runtime.py`, `core/gemini_runtime.py`
- **Katman 1 (Platform ve Kalıcı Kayıt / Süreç Maliyeti):** `core/process_tree.py`, `core/async_snapshot.py`, `core/low_spec_optimizer.py`

### Kapsam Dışı ve Dokunulmayan Alanlar:
- Notion ajanı ve ASTER / Warband resmi olarak kapsam dışıdır.
- `gui.py`, `ui/*`, `main.py`, `quartz_entry.py`, `orchestrator`, izin/broker modülleri, kurulum/login ayarları ve paket/CI dosyaları salt okunur tutulmuştur; hiçbir harici dosyaya dokunulmamıştır.

---

## 2. Kapsamlı Yaşam Döngüsü Haritası (Lifecycle Mapping Table)

Aşağıdaki tablo her üç CLI runtime'ın tüm yaşam döngüsü adımlarını, sahipliklerini ve durum semantiklerini tek bir sözleşmede eşler:

| Özellik / Adım | `CodexRuntime` (`core/codex_runtime.py`) | `AntigravityRuntime` (`core/antigravity_runtime.py`) | `GeminiRuntime` (`core/gemini_runtime.py`) |
| :--- | :--- | :--- | :--- |
| **Piramit Katmanı** | Katman 3 (CLI Adaptörü) | Katman 3 (CLI Adaptörü) | Katman 3 (CLI Adaptörü) |
| **Temel CLI** | OpenAI `codex` CLI | Google `agy` CLI | Google `gemini` CLI |
| **Giriş Metodu (`start`)** | `start(prompt, project_path, *, sandbox, approval, timeout="10m", ...)` | `start(prompt, project_path, *, write, full_access, timeout="10m", ...)` | `start(prompt, project_path, **kwargs)` (miras alır, effort="medium" şartı) |
| **İstem İletimi (Prompt Input)** | `process.stdin.write(text); process.stdin.close()` (STDIN pipe) | `-p <text>` (CLI argümanı, STDIN=`DEVNULL`) | `-p <text>` (CLI argümanı, STDIN=`DEVNULL`) |
| **Süreç Başlatma** | `subprocess.Popen(..., creationflags=CREATE_NO_WINDOW)` | `subprocess.Popen(..., creationflags=CREATE_NO_WINDOW)` | `subprocess.Popen(..., creationflags=CREATE_NO_WINDOW)` |
| **Arka Plan Thread'leri** | `stdout_thread`, `stderr_thread`, `wait_thread` (daemon) | `stdout_thread`, `stderr_thread`, `wait_thread` (daemon) | `stdout_thread`, `stderr_thread`, `wait_thread` (daemon) |
| **Süreç Sahipliği** | `self._processes[run_id] = process` | `self._processes[run_id] = process` | `self._processes[run_id] = process` |
| **Tek Yazıcı Kilidi** | `self._writers[project_key] = run_id` | `self._writers[project_key] = run_id` | `self._writers[project_key] = run_id` |
| **Durum Sorgulama (`get`)** | `get(run_id) -> dict` (kopyalanmış ve dilimlenmiş events/errors/commands) | `get(run_id) -> dict` (kopyalanmış progress_log/events/errors) | `get(run_id) -> dict` |
| **İptal İsteği (`cancel`)** | `cancel_requested=True`, `status="cancelling"`, `stop_process_tree` | `cancel_requested=True`, `status="cancelling"`, `stop_process_tree` | `cancel_requested=True`, `status="cancelling"`, `stop_process_tree` |
| **Çıkış Doğrulama (`_wait`)** | `process.wait(timeout=timeout_sec)` $\rightarrow$ exit code & stream join | `process.wait(timeout=timeout_sec)` $\rightarrow$ exit code & stream join | `process.wait(timeout=timeout_sec)` $\rightarrow$ exit code & stream join |
| **Kapanış (`shutdown`)** | Tüm aktif süreçler için `cancel(run_id)` çağrılır | Tüm aktif süreçler için `cancel(run_id)` çağrılır | Süreçler durdurulur + geçici `_settings_paths` temizlenir |
| **Terminal Durumlar** | `completed`, `failed`, `cancelled` | `completed`, `failed`, `cancelled` | `completed`, `failed`, `cancelled` |
| **CLI Oturumu (Session ID)** | `record["thread_id"]` (olay: `thread.started`) | `record["conversation_id"]` (olay: `init` / `result`) | `record["conversation_id"]` (`gemini:<session_id>`) |
| **Uygulama Görev ID** | `record["squad_task_id"]` | `record["squad_task_id"]` | `record["squad_task_id"]` |
| **Sağlayıcı Çalıştırma ID** | `record["id"] = uuid.uuid4().hex` (`run_id`) | `record["id"] = uuid.uuid4().hex` (`run_id`) | `record["id"] = uuid.uuid4().hex` (`run_id`) |
| **Hata Çıkışı Semantiği** | `errors`: turn.failed, error event, stderr, timeout, non-zero exit | `errors`: result.error, denied_actions, stderr, timeout, non-zero exit | `errors`: tool error, stderr, timeout, non-zero exit |

---

## 3. Sahip Olunan Süreç Ağacı Mekanizması ve Stop Doğrulaması (`core/process_tree.py`)

1. **Katı Sahiplik İlkesi:**
   - Yalnızca `process: subprocess.Popen` nesnesinin `pid` değeri üzerinden `psutil.Process(process.pid).children(recursive=True)` ile tespit edilen doğrudan ve torun çocuk süreçler listelenir.
   - Sistemde çalışan başka süreçlere PID tahmini, isim eşleştirme (`taskkill /im ...`) veya rastgele aramayla kesinlikle müdahale edilmez.
2. **Tersine Hiyerarşik Sonlandırma:**
   - Önce en derin torun süreçler (`reversed(descendants)`), ardından doğrudan çocuklar, en son ana süreç sonlandırılır (`terminate()`).
   - Kalan canlı süreçler için `wait_procs` ile belirlenen süre beklenir; kapanmayanlar `kill()` ile zorla kapatılır.
3. **İptal İsteği ile Gerçek Exit Doğrulamasının Ayrımı:**
   - Kullanıcı veya sistem Stop talep ettiğinde:
     - `record["cancel_requested"] = True`
     - `record["status"] = "cancelling"` (işlem durduruluyor, süreç ağacı sonlandırma sinyali gönderildi)
   - Süreç gerçekten sonlanıp `process.poll() is not None` teyit edilene ve stream thread'leri birleşene kadar durum terminal `"cancelled"` yapılmaz.
   - Süreç ve çocukları kapandığında `_wait` izleyicisi durumu `"cancelled"` olarak mühürler.
   - İptal isteği ile gerçek çıkış doğrulamasının ayrılması sayesinde UI'a sahte veya erken başarı/durduruldu bilgisi verilmez.
4. **Hataların Saklanmaması:**
   - Beklenmeyen süreç, izin veya IO istisnaları yutulmaz; `record["errors"]` içerisine teşhis kaydı olarak eklenir.

---

## 4. Kimlik Ayrımı (Task vs Run vs Session)

Mimari piramitte belirtilen ortak sözleşmeye tam uyum sağlanmıştır:

```
[task_id / squad_task_id]  -> Kullanıcı veya Squad'ın üst seviye hedefi (Application level)
       │
       ▼
[run_id (record["id"])]    -> Belirli bir provider runtime çalıştırma UUID'si (Execution level)
       │
       ▼
[session_id]               -> CLI oturumu (Codex: thread_id, Antigravity: conversation_id)
```

- `run_id` kayıtları yeni bir küresel task motoruna dönüştürülmemiştir; runtime'lar yalnızca kendi iç çalıştırma sözlüklerini (`self._runs[run_id]`) yönetir.
- Üst seviye `task_id` bilgisi `record["squad_task_id"]` alanında korelasyon amacıyla taşınır, asla `run_id` yerine kullanılmaz.

---

## 5. Gerçek Yaşam Döngüsü Kusurları ve Yapılan Düzeltmeler

Yapılan kaynak kod incelemesi ve test denemelerinde tespit edilen 6 somut kusur düzeltilmiştir:

### Kusur 1: `CodexRuntime`'da `_wait()` İçinde Timeout Bulunmaması
- **Bulgu:** `CodexRuntime.start()` parametrelerinde `timeout` yoktu ve `_wait()` içindeki `code = process.wait()` süresiz bloklanıyordu. CLI askıda kaldığında veya çocuk süreç kilitlendiğinde izleyici thread sonsuza kadar takılı kalıyor, `_writers` kilidi asla serbest bırakılmıyordu.
- **Düzeltme:** `CodexRuntime.start()` metoduna `timeout="10m"` parametresi eklendi, `_parse_timeout_seconds` ile çözümlendi ve `_wait()` içinde `process.wait(timeout=timeout_sec)` ile `TimeoutExpired` durumunda `stop_process_tree` çağrılarak hata `record["errors"]`a yazıldı.

### Kusur 2: `_wait()` İçindeki Beklenmeyen Hatalarda Tek Yazıcı Kilidinin Takılı Kalması
- **Bulgu:** `_wait()` içinde stream join veya status güncellemesi sırasında beklenmeyen bir `Exception` fırlatıldığında `self._writers.pop(project_key, None)` satırına ulaşılamıyordu. Bu durum projeyi kalıcı olarak kilitleyerek sonraki tüm yazma görevlerini `"This project already has an active write-capable agent"` hatasıyla engelliyordu.
- **Düzeltme:** `_wait()` gövdesi `try...finally:` bloğuna alındı; `_processes` ve `_writers` temizliğinin her koşulda icra edilmesi garanti edildi.

### Kusur 3: Unauthenticated / Unready Durumda Probe Önbelleğinin Atlanması (Polling Fırtınası)
- **Bulgu:** `CodexRuntime.probe()` metodunda:
  ```python
  if not force and cached and cached.get("ready") and (now - cached_at < self.PROBE_TTL):
      return dict(cached)
  ```
  Koşulu yalnızca `cached.get("ready")` True olduğunda önbelleği kullanıyordu. Kullanıcı henüz login olmadığında `ready` False olduğu için her UI polling döngüsünde (`AsyncSnapshot` üzerinden) önbellek yok sayılıp `codex --version` ve `codex login status` subprocess'leri yeniden çalıştırılıyordu.
- **Düzeltme:** Önbellek kontrolü `cached.get("ready")` şartına bağımlı olmaktan çıkarıldı; `force=False` olduğu sürece negatif (hazır olmayan) durumlar da `PROBE_TTL` boyunca önbellekten dönülerek polling kaynaklı süreç yükü engellendi. `_SHARED_PROBE_CACHE` aynı şekilde güncellendi.

### Kusur 4: Provider Yokluğunda `AntigravityRuntime` / `GeminiRuntime`'ın `__init__`'te Çökmesi
- **Bulgu:** `AntigravityRuntime.__init__` içinde `self._find_executable(executable)` çağrısı try/except ile korunmuyordu. CLI kurulu olmadığında nesne örneği oluşturulurken doğrudan `FileNotFoundError` fırlatılıyordu (CodexRuntime ise bunu yakalayıp `installed: False` dönüyordu).
- **Düzeltme:** `AntigravityRuntime.__init__` try/except ile sarıldı, `self.executable = None` ve `self._init_error` kaydedildi. `probe()` çağrıldığında subprocess başlatılmadan doğrudan `{"installed": False, "ready": False, ...}` dönmesi sağlandı.

### Kusur 5: Geç Gelen Çıktının (`Late Output`) Terminal Sonucu Ezmesi
- **Bulgu:** Süreç sonlandıktan veya iptal edildikten sonra gecikmeli gelen stdout satırları `_read_stdout` tarafından `record["result"]` üzerine yazılabiliyordu.
- **Düzeltme:** `_read_stdout` ve `_read_stderr` içinde kayıt durumu `self.TERMINAL` içinde ise `record["result"]` alanının ezilmesi engellendi. Ayrıca boru hattı kapanışındaki `(OSError, ValueError)` istisnaları korumaya alındı.

### Kusur 6: `process_tree` Sonlandırma Sonrası Exit Teyidi
- **Bulgu:** `stop_process_tree` `None` dönüyor ve psutil temizliği sonrası Python'ın `process` nesnesi üzerinde `poll()` çağrısı yapmıyordu; bu da Popen `returncode` değerinin güncellenmesini geciktirebiliyordu.
- **Düzeltme:** `stop_process_tree` açık bir `bool` dönecek şekilde güncellendi ve çıkışta `process.poll()` tazelenerek `process.poll() is not None` teyidi sağlandı.

---

## 6. Bütün Süreç Ağacı ile CPU/RAM Ölçümleri

Ölçümler `core/low_spec_optimizer.py` içerisindeki `measure_process_tree_resources` motoru ve `scripts/measure_runtime_efficiency_pyramid.py` betiği ile bütünleşik olarak yapılmıştır.

### Ölçüm Ortamı:
- **İşletim Sistemi:** Windows (win32)
- **Mantıksal Çekirdek:** 2 çekirdek
- **Ölçüm Yöntemi:** Tüm süreç ağacı (`psutil.Process(root).children(recursive=True)`) üzerinden RSS, özel bellek (USS) ve CPU yüzdesi.

### Canlı Ölçüm Tablosu:

| Profil | Durum Etiketi | Süreç Sayısı (Tree) | Toplam RSS | Özel Bellek (USS) | Toplam CPU | Açıklama / Ek Metrik |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Idle (Boşta)** | `LIVE_MEASURED` | 1 | 24.88 MB | 10.31 MB | 0.0 % | Temel Python süreç ağacı |
| **Startup (Açılış)** | `LIVE_MEASURED` | 1 | 31.75 MB | 14.83 MB | 0.0 % | Runtime + probe önbellek açılışı (291.86 ms) |
| **Active Running (Çalışma)** | `LIVE_MEASURED` | 4 | 71.44 MB | 31.04 MB | 11.45 % | Ana süreç + çocuk ve torun CLI süreç ağacı |
| **Stop / Cancellation (İptal)** | `LIVE_MEASURED` | 1 | 32.69 MB | 15.25 MB | 0.0 % | 4 süreçten 1 sürece düşüş, Stop gecikmesi: **32.59 ms** |
| **Shutdown / Trim (Kapanış)** | `LIVE_MEASURED` | 1 | 32.58 MB | 15.25 MB | 0.0 % | Süreç ağacı kapatıldı, bellek trim uygulandı |

*Not: Ölçümler simüle değil, Windows işletim sistemi üzerinde gerçek süreç ağaçları başlatılarak canlı (`LIVE_MEASURED`) kaydedilmiştir.*

---

## 7. Test Kapsamı ve Sonuçları

### 1. Yeni Yaşam Döngüsü Test Paketi (`tests/test_pyramid_runtime_lifecycle.py`):
13 test senaryosu:
- `test_failed_start_validations`: Boş prompt, geçersiz dizin ve geçersiz sandbox denetimleri (**PASS**)
- `test_normal_exit_codex`: Codex normal akış, stream parsing ve yazıcı kilidi serbest kalması (**PASS**)
- `test_normal_exit_antigravity`: Antigravity normal akış ve yazıcı kilidi serbest kalması (**PASS**)
- `test_timeout_codex_stops_process_and_records_error`: Codex zaman aşımında süreç ağacı durdurma ve hata kaydı (**PASS**)
- `test_timeout_antigravity_stops_process_and_records_error`: Antigravity zaman aşımında süreç ağacı durdurma (**PASS**)
- `test_stop_cancellation_codex`: Codex iptal isteği $\rightarrow$ cancelling $\rightarrow$ cancelled geçişi ve idempotent ikinci çağrı (**PASS**)
- `test_stop_cancellation_antigravity`: Antigravity iptal akışı (**PASS**)
- `test_consecutive_writer_runs_on_same_project_succeed`: Aynı projede ardışık iki yazma görevinin kilit çakışması olmadan çalışabilmesi (**PASS**)
- `test_provider_absence_codex_and_antigravity`: CLI bulunamadığında çökmeden `installed: False` dönülmesi ve güvenli hata (**PASS**)
- `test_child_cleanup_terminates_descendants`: Çocuk ve torun süreçlerin yetim kalmadan temizlenmesi (**PASS**)
- `test_late_output_isolation_codex`: Terminal duruma geçmiş kayda geç gelen çıktının sonucu bozamaması (**PASS**)
- `test_probe_caching_does_not_spawn_subprocess_on_repeated_poll`: UI polling sırasında mükerrer CLI login/probe süreçlerinin engellenmesi (**PASS**)
- `test_gemini_runtime_lifecycle`: Gemini runtime doğrulama ve yokluk yönetimi (**PASS**)

**Sonuç: 13/13 test PASS (2.24s).**

### 2. Sahip Olunan Tüm Testlerin Birlikte Çalıştırılması:
```powershell
python -B -m unittest tests/test_pyramid_runtime_lifecycle.py tests/test_codex_runtime.py tests/test_antigravity_runtime.py tests/test_process_tree.py tests/test_low_spec_optimization.py
```
**Sonuç: 39/39 test PASS (4.98s).**

### 3. Syntax ve Güvenlik Denetimleri:
- `python -B scripts/check_python_syntax.py`: **234 files OK**
- `python -B scripts/audit_publish.py --history`: **PASS (0 findings, 368 files, 0 secrets)**

---

## 8. SOURCE / BUILT / LIVE Ayrımı

- **SOURCE / STATIC:**
  - Tüm kod değişiklikleri ve sözleşmeler `core/codex_runtime.py`, `core/antigravity_runtime.py`, `core/gemini_runtime.py`, `core/process_tree.py` dosyalarında statik olarak doğrulanmıştır.
- **BUILT:**
  - Dağıtılmış bağımsız EXE paketi oluşturulmamıştır (talimat gereği: paketleme ve birleştirme tek elden Codex tarafından yapılacaktır).
- **LIVE:**
  - Süreç ağacı bellek, CPU ve Stop gecikmesi ölçümleri canlı Windows oturumunda `psutil` ile ölçülmüş ve `LIVE_MEASURED` olarak belgelenmiştir.

---

## 9. Codex için Entegrasyon İstekleri (Integration Requests)

1. **`core/multi_agent_service.py` ve `core/natural_desktop.py` Çağrılarında `timeout` Desteği:**
   - `CodexRuntime.start()` artık `timeout="10m"` (veya float saniye) parametresini kabul etmektedir.
   - `MultiAgentService.dispatch_codex` ve `NaturalDesktopTask` çağrılarında ihtiyaç halinde özel görev zaman aşımı iletilebilir.
2. **Korelasyon Sözleşmesi:**
   - `MultiAgentService`'in `_links[run_id]` sözlüğünde tuttuğu `coordination_status` ile runtime'ın `record["status"]` alanı uyumludur (`cancelling` $\rightarrow$ `cancelled`).
   - `task_id` uygulama seviyesinde `squad_task_id` parametresi olarak iletilmeye devam edebilir.

---

## 10. Geri Alma Yolu (Rollback Plan)

Tüm değişiklikler müstakil bir branch (`antigravity/pyramid-runtime-20261101`) ve çalışma ağacında (`quartz-pyramid-runtime`) yapılmıştır. Geri almak için:
```powershell
git checkout codex/architecture-pyramid-20261101
git branch -D antigravity/pyramid-runtime-20261101
```
komutları ile taban commit `047fa6e` durumuna anında ve yan etkisiz dönülebilir.
