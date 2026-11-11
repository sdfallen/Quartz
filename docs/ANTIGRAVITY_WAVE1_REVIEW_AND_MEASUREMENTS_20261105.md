# Quartz Dalga 1 Bağımsız İnceleme ve Ölçüm Raporu (5 Kasım 2026)

- **Yazar:** Antigravity (Gemini)
- **Dal:** `antigravity/wave0-wave1-analysis-20261105`
- **Worktree:** `C:\Users\LENAVO\.gemini\antigravity\worktrees\quartz-wave0-wave1-20261105`
- **Taban SHA (`main`):** `92751a3e0d9e673898093e4a6cd897bcdf93ee55`
- **İncelenen Codex Dalı / Commit'ler:** `codex/wave0-review-20261105` (`837b44f`, `e6e1170`, `03b3be2`)

---

## 1. Codex'in Görev Sınavı Koşucusu (`task_exam_runner.py`) Bağımsız İncelemesi

İncelenen dosyalar (salt okunur, hiçbir Codex dosyası değiştirilmedi):
- `scripts/task_exam_runner.py`
- `scripts/task_exam_catalog.json`
- `docs/TASK_EXAM_RUNNER.md`
- `docs/TASK_EXAM_SCRIPT_INVENTORY_20261105.md`
- `tests/test_task_exam_runner.py`

### 1.1. Gerçek Komut Doğrulaması (`unittest` ve `task_exam_runner.py --execute`)

```text
> python -B -m unittest tests.test_task_exam_runner -v
Ran 11 tests in 0.054s
OK

> python -B scripts/task_exam_runner.py --manifest docs/task_exam_manifest.example.json --output <TEMP_DIR> --execute
{"id": "infra-regression-only", "status": "VERIFIED", "level": "TESTED", "duration_seconds": 1.427, "step_count": null}
{"id": "synthetic-process-only", "status": "VERIFIED", "level": "TESTED", "duration_seconds": 3.821, "step_count": null}
```

### 1.2. Dört Kritik Soruya Göre Bulgular (`dosya:satır`)

#### Soru A: Model "tamamlandı" dediğinde veya yalnız çıkış kodu `0` olduğunda `VERIFIED` üretebiliyor mu?
- **Hayır, genel olarak engellenmiş (`scripts/task_exam_runner.py:70-83`):**
  - `verdict(adapter, stdout, code)` fonksiyonu `code != 0` ise doğrudan `('FAILED', None)` döner (`scripts/task_exam_runner.py:71`).
  - `code == 0` olduğunda serbest metin ("tamamlandı" vb.) hiçbir zaman kabul edilmez; yalnız iki adaptör (`unittest` ve `process-benchmark`) tanımlıdır, diğer tüm adaptörler `('NOT VERIFIED', None)` döner (`scripts/task_exam_runner.py:83`).
  - `process-benchmark` adaptörü (`scripts/task_exam_runner.py:77-82`) JSON çıktısında `data['stop_cancellation']['stop_verified'] is True` koşulunu zorunlu tutar.
- **Bulgu B1 (Düşük/Orta — `unittest` adaptöründe `Ran 0 tests` durumu, `scripts/task_exam_runner.py:72-76, 116`):**
  - `scripts/task_exam_runner.py:74` satırındaki `re.search(r'Ran (\d+) tests? in .*\n\s*OK(?: \(skipped=(\d+)\))?', stdout)` ifadesi `int(match[1]) > 0` kontrolü yapmıyor. Eğer yanlış bir test hedefi yüzünden `unittest` `Ran 0 tests in 0.000s\n\nOK` çıktısı ve `0` çıkış kodu üretirse `verdict('unittest', ...)` bunu `('VERIFIED', {'tests': 0, 'skipped': 0})` olarak işaretler.
  - Ayrıca `scripts/task_exam_runner.py:116` satırında `verdict` fonksiyonuna `logs + '\n' + stderr` birleştirilerek verildiği için, alt sürecin `stdout` çıktısında sahte bir `Ran 1 test in 0.001s\nOK` metni yer alırsa regex bunu da eşleştirebilir (`unittest` çıktısı yalnız `stderr` üzerinde veya `int(match[1]) > 0` koşuluyla doğrulanmalıdır).

#### Soru B: Kişisel veri ya da ekran kanıtı repoya sızabilir mi?
- **Koşucu düzeyinde repo içi çıktı engellenmiş (`scripts/task_exam_runner.py:30-35`):**
  - `private_output(path)` fonksiyonu `any((p / '.git').exists() for p in (path, *path.parents))` kontrolüyle hem normal git klonlarını (`.git` dizini) hem de git worktree'lerini (`.git` dosyası) reddeder; ayrıca var olan bir dizinin üzerine yazmayı da `if path.exists(): raise ValueError('Use a new evidence directory')` ile engeller.
  - Ham `stdout.log` ve `stderr.log` yalnız repo dışındaki `<output>/<task_id>/` klasörüne yazılır; `result.json` içine yalnız SHA-256 özetleri (`log_sha256`, `scripts/task_exam_runner.py:125`) kaydedilir ve konsola yalnız `('id', 'status', 'level', 'duration_seconds', 'step_count')` basılır (`scripts/task_exam_runner.py:165`).
- **Bulgu B2 (Mimari Koruma Notu — `labs/` altına yazan 16 kabul betiği, `scripts/task_exam_catalog.json`):**
  - Katalogdaki 24 betikten 16'sı (`accept_desktop_cancellation.py:61`, `desktop_mcp_acceptance.py:20`, `natural_gateway_acceptance.py:26`, `desktop_chat_acceptance.py` vb.) çalıştırıldıklarında doğrudan repo içindeki `ROOT / "labs" / ...` dizinine JSON/ekran görüntüsü yazar.
  - Şu an bu 16 betiğin tamamında `"adapter": null` olduğu için `command_for` (`scripts/task_exam_runner.py:62-63`) bunları `BLOCKED` durumunda tutar ve çalıştırmaz. Ancak Dalga 2/3'te bu betiklere adaptör bağlanırken, çıktı yolunun repo içindeki `labs/` yerine `private_output` altındaki kanıt klasörüne yönlendirilmesi zorunludur; aksi halde repo çalışma ağacına ekran görüntüsü/log sızar.

#### Soru C: `Ctrl+C` / Durdur'da süreç ağacı temizleniyor mu?
- **`process.wait` sırasında gelen `TimeoutExpired` ve `KeyboardInterrupt` yakalanıyor (`scripts/task_exam_runner.py:105-111, 166`):**
  - `process.wait(timeout=timeout)` sırasında zaman aşımı veya `KeyboardInterrupt` oluşursa `clean = stop_process_tree(process, timeout=3)` çağrılır (`scripts/task_exam_runner.py:107`), `cleanup_confirmed = clean` kaydedilir ve `main()` döngüsü `if row.get('interrupted'): break` (`scripts/task_exam_runner.py:166`) ile sonraki görevlere geçmeden durur.
- **Bulgu B3 (Orta — Normal çıkışta yetim alt süreç kontrolü eksik ve `stop_process_tree` sırasında ikinci `Ctrl+C` koruması yok, `scripts/task_exam_runner.py:105-112`):**
  1. `CodexRuntime._wait` ve `AntigravityRuntime._wait` süreç normal çıkış koduyla (`code == 0`) bitse bile `owned_cleanup_pending(process, include_root=False)` / `wait_for_owned_cleanup` ile alt süreç kalıp kalmadığını doğrular. `run_task` (`scripts/task_exam_runner.py:105-112`) ise `process.wait(timeout=timeout)` normal döndüğünde alt süreç ağacını (`owned_cleanup_pending(process, include_root=False)`) kontrol etmez; kök betik çıkıp arkada yetim alt süreç bıraktığında `cleanup_confirmed = True` ve `VERIFIED` üretebilir.
  2. İlk `Ctrl+C` sonrasında `stop_process_tree(process, timeout=3)` çalışırken kullanıcı ikinci kez `Ctrl+C` gönderirse veya `Popen` ile `try: code = process.wait(...)` arasındaki pencerede (`scripts/task_exam_runner.py:99-104`) `KeyboardInterrupt` gelirse süreç ağacı temizlenmeden istisna dışarı fırlar.

#### Soru D: Betik sınıflandırması (`scripts/task_exam_catalog.json` ve `docs/TASK_EXAM_SCRIPT_INVENTORY_20261105.md`) doğru mu?
- **SHA-256 ve Sözdizimi Bütünlüğü:** Katalogdaki 24 betiğin tamamının (`scripts/*.py` ve `scripts/rea_validation/workbench_acceptance.py`) SHA-256 özetleri gerçek dosyalarla birebir eşleşmektedir (`SHA mismatches: []`).
- **Bulgu B4 (Düşük — 2 betikte `FakeBackend` / `NoInputBackend` kullanımı ve kapsam notu):**
  - `scripts/accept_desktop_cancellation.py` (`REQUIRES_ACCOUNT`) ve `scripts/desktop_mcp_acceptance.py` (`REQUIRES_ACCOUNT`) gerçek masaüstü girişi yapmaz (`FakeBackend` kullanır), bu yüzden `REQUIRES_ACCOUNT` sınıflandırması doğrudur; ancak her iki betik de `ROOT / "labs"` altına dosya yazdığı için (`accept_desktop_cancellation.py:61`, `desktop_mcp_acceptance.py:20,62`) `summary` alanlarında `labs/` yazma yan etkisinin belirtilmesi yararlı olur.
  - `scripts/` altında toplam 53 Python betiği vardır; katalog 24 kabul/ölçüm betiğini kapsamaktadır (`check_python_syntax.py`, `run_safe_tests.py`, `audit_publish.py` gibi yardımcı/CI betikleri ve `probe_*` betikleri katalog dışındadır). Bu kapsam seçimi makuldür ancak envanter belgesinde toplam 53 betikten 24 kabul/ölçüm betiğinin seçildiği açıkça not edilmelidir.

---

## 2. Sağlayıcı Hata Taksonomisi Zaman Aşımı Testi (`tests/test_provider_failure_taxonomy.py`)

`tests/test_provider_failure_taxonomy.py` dosyasına `test_6_timeout_stops_process_tree_records_error_and_releases_writer_lock` testi eklendi. Test hem `CodexRuntime` hem de `AntigravityRuntime` için yazıcı (`writer`) modunda zaman aşımı oluştuğunda:
1. `stop_process_tree(..., timeout=5)` çağrıldığını,
2. Görev durumunun `"failed"` olduğunu ve `"Task timed out after ..."` hatasının `errors` listesine kaydedildiğini,
3. Süreç çıkışının doğrulandığını (`process_exit_confirmed is True`) ve `runtime._writers` üzerindeki proje yazıcı kilidinin serbest bırakıldığını (`self.assertNotIn(project_key, runtime._writers)`) doğrular.

### Gerçek Test Çıktısı
```text
> python -B -m unittest tests.test_provider_failure_taxonomy -v
test_1_quota_exhaustion_codex_and_antigravity_format_and_no_retry (tests.test_provider_failure_taxonomy.ProviderFailureTaxonomyTests.test_1_quota_exhaustion_codex_and_antigravity_format_and_no_retry) ... ok
test_2_auth_drop_and_stale_session_retry_policy (tests.test_provider_failure_taxonomy.ProviderFailureTaxonomyTests.test_2_auth_drop_and_stale_session_retry_policy) ... ok
test_3_cli_crash_and_silent_zero_exit_never_report_false_success (tests.test_provider_failure_taxonomy.ProviderFailureTaxonomyTests.test_3_cli_crash_and_silent_zero_exit_never_report_false_success) ... ok
test_4_network_drop_truncated_stream_mid_turn_fails_cleanly (tests.test_provider_failure_taxonomy.ProviderFailureTaxonomyTests.test_4_network_drop_truncated_stream_mid_turn_fails_cleanly) ... ok
test_5_unconfirmed_child_cleanup_keeps_writer_and_process_fenced (tests.test_provider_failure_taxonomy.ProviderFailureTaxonomyTests.test_5_unconfirmed_child_cleanup_keeps_writer_and_process_fenced) ... ok
test_6_timeout_stops_process_tree_records_error_and_releases_writer_lock (tests.test_provider_failure_taxonomy.ProviderFailureTaxonomyTests.test_6_timeout_stops_process_tree_records_error_and_releases_writer_lock) ... ok

----------------------------------------------------------------------
Ran 6 tests in 1.783s

OK
```

---

## 3. Boşta Alt Süreç Maliyeti Ölçümü (10 Dakika) ve Düzeltme / Integration Request

### 3.1. Gerçek Ölçüm Sonuçları

1. **Gerçek Duvar Saati Ölçümü (Başlatılmış `.squad/messages.db` olan projede):**
   - İlk `MultiAgentService.status()` çağrısı (`t = 0s`): **10.03 saniye** sürdü ve **9 işletim sistemi alt süreci** başlattı:
     - `codex.exe --version`
     - `codex.exe login status`
     - `agy.exe --version`
     - `agy.exe -p /model` (`--output-format stream-json --mode ask`)
     - `agy.exe models`
     - `squad.exe --version`
     - `squad.exe agents --json`
     - `squad.exe task list`
     - `squad.exe history`
   - Sonraki her 15 saniyelik `AsyncSnapshot` yenilemesi (`t = +15s`, `0.73 saniye` sürdü): **4 `squad.exe` alt süreci** başlattı (`--version`, `agents --json`, `task list`, `history`).
2. **10 Dakikalık (`600s`, 1.5s aralıklarla 400 boşta UI yoklaması) Tam Sayım:**

| Proje Durumu | `squad.exe` | `codex.exe` | `agy.exe` | 10 Dakika Toplamı | Komut Dağılımı |
|---|---:|---:|---:|---:|---|
| **Squad Başlatılmış Proje** (`.squad/messages.db` mevcut, örn. varsayılan `squad-pilot`) | **160** | **4** | **6** | **170 alt süreç** | `40× squad --version`, `40× squad agents --json`, `40× squad task list`, `40× squad history`, `2× codex --version`, `2× codex login status`, `2× agy --version`, `2× agy -p /model`, `2× agy models` |
| **Squad Başlatılmamış / Warband Projesi** (`.squad/messages.db` yok) | **40** | **4** | **6** | **50 alt süreç** | `40× squad --version`, `2× codex --version`, `2× codex login status`, `2× agy --version`, `2× agy -p /model`, `2× agy models` |

### 3.2. Kök Neden ve Kendi Alanımızdaki (`core/async_snapshot.py`) Küçük Düzeltme

1. **`core/async_snapshot.py` (Antigravity Sahipliği — Düzeltildi ve Test Edildi):**
   - **Sorun:** `AsyncSnapshot.read()` içinde `self.attempted = now` yenileme *başlarken* (`t = 0.0s`) atanıyor, `_refresh()` bittiğinde (`t = 10.03s`) güncellenmiyordu. Bu nedenle ilk `10.03` saniyelik ağır CLI yoklaması bittikten yalnızca `4.97` saniye sonra (`t = 15.0s`) ikinci yenileme tetikleniyordu.
   - **Düzeltme:** `core/async_snapshot.py:54-58` içinde `_refresh` tamamlandığında (ve `generation == self.generation` iken) `now = self.clock(); self.attempted = now` güncellenerek iki yenileme arasında tamamlama zamanından itibaren tam `ttl` (`15s`) boşluk bırakılması sağlandı.
   - **Test:** `tests/test_runtime_efficiency_idle_snapshot.py` eklendi (`Ran 1 test - OK`) ve mevcut `tests/test_reliability_kernel.py` (`Ran 12 tests - OK`) doğrulandı.

### 3.3. Codex Alanı İçin Integration Request (`IR-AGY-IDLE-SQUAD-01`)

- **Hedef Dosyalar (Codex Sahipliği):** `core/multi_agent_service.py` (`status()` ve `_task_squad_status()`), `core/agent_chat.py` (`self._diagnostics`)
- **Neden:** `CodexRuntime` ve `AntigravityRuntime` kendi içlerinde `PROBE_TTL = 300.0` (5 dakika) önbelleğe sahipken, `MultiAgentService.status()` (`core/multi_agent_service.py:240-251`) her `AsyncSnapshot` yenilemesinde (15 saniyede bir) önbelleksiz olarak 4 adet `squad.exe` alt süreci (`--version`, `agents --json`, `task list`, `history`) başlatmakta ve boşta 10 dakikada **160 `squad.exe` süreci** üretmektedir.
- **Önerilen Küçük Sözleşme / Değişiklik:**
  1. `MultiAgentService` içinde `squad.exe --version` (`squad.status()`) sonucunu `self._probe_cache` gibi `300s` TTL ile önbelleğe alın (yalnızca `.squad/messages.db` varlığı `squad.initialized` özelliğiyle dosya sisteminden ucuzca kontrol edilsin).
  2. `MultiAgentService.status()` içinde `.squad/messages.db` yoksa `squad.agents()`, `squad.tasks()`, `squad.history()` çağrılmasın; `.squad/messages.db` varsa dosyanın `(mtime_ns, size)` ikilisi değişmediği ve aktif bir grup/Squad görevi (`self._collaborations`) çalışmadığı sürece son okunan `(agents, tasks, history)` önbellekten döndürülsün.
- **Beklenen Etki:** Boşta 10 dakikadaki `squad.exe` alt süreç sayısı **160'tan 4'e** (veya önbellek sonrası **0'a**), toplam boşta alt süreç sayısı **170'ten 12'ye** düşer.
- **Önerilen Test:** `tests/test_multi_agent_service.py` içinde `.squad/messages.db` değişmediğinde ardışık iki `svc.status()` çağrısının ikinci kez `squad.exe` başlatmadığını doğrulayan birim testi.

---

## 4. Sistem ve Quartz Bellek (RAM) Dağılımı Ölçümü

Kurulu `Quartz.exe` kullanıcıya sorulmadan ve Codex masaüstü testiyle çakışmaması için **açılmamıştır**. Mevcut sistem belleğinin (`7.92 GB` toplam) `psutil.process_iter` (USS — Private Unique Set Size ve RSS) ile yapılan gerçek ölçümü aşağıdadır:

### 4.1. Genel Sistem Özeti
- **Toplam Fiziksel RAM:** `7.92 GB`
- **Kullanılan RAM:** `6.87 GB` (`%86.8`) — önceki anlık ölçümde `7.14 GB` (`%90.1`)
- **Boş / Kullanılabilir RAM:** `1.04 GB` — önceki anlık ölçümde `0.78 GB`
- **Erişilebilir Süreçlerin Toplam Özel Belleği (USS):** `5.08 GB` (geri kalanı Windows çekirdeği, Non-paged/Paged Pool ve paylaşılan DLL sayfalarıdır)

### 4.2. Quartz Süreçleri vs. Diğer Programlar

| Kategori / Uygulama Grubu | Süreç Sayısı | Özel Bellek (USS) | Çalışma Kümesi (RSS) | Pay / Açıklama |
|---|---:|---:|---:|---|
| **Quartz (`Quartz.exe` / `QuartzDesktopMCP.exe`)** | **2** | **0.2 MB (`0.0002 GB`)** | **15.3 MB (`0.015 GB`)** | `Quartz.exe` kapalı; yalnız 2 adet boşta `QuartzDesktopMCP.exe` (`PID 17580`, `PID 20244`) bellekte `0.2 MB` USS yer kaplıyor |
| **Claude Masaüstü / Ajan (`claude.exe`)** | 12 | **905.6 MB (`0.88 GB`)** | 1197.2 MB | Sistemdeki en büyük kullanıcı süreci grubu |
| **Windows Sistem Hizmetleri (`svchost.exe` + `MsMpEng.exe` + `dwm.exe` + `explorer.exe` + `SearchIndexer.exe` + `MemCompression`)** | 88 | **1397.9 MB (`1.37 GB`)** | 1516.8 MB | Windows işletim sistemi ve Defender (`MsMpEng.exe` tek başına `335.0 MB` USS) |
| **OpenAI Codex Masaüstü Uygulaması (`ChatGPT.exe` + `codex.exe` + `codex-windows-sandbox-service.exe`)** | 19 | **875.6 MB (`0.86 GB`)** | 1352.4 MB | Geliştirme/inceleme ortamındaki Codex masaüstü uygulaması ve `codex.exe app-server` |
| **Antigravity IDE (`Antigravity.exe` + `language_server.exe`)** | 7 | **682.1 MB (`0.67 GB`)** | 864.1 MB | Geliştirme/inceleme ortamındaki Antigravity IDE ve dil sunucusu |
| **Steam (`steamwebhelper.exe`)** | 8 | **298.5 MB (`0.29 GB`)** | 431.6 MB | Arka plan kullanıcı uygulaması |
| **Notion (`Notion.exe`)** | 9 | **291.6 MB (`0.28 GB`)** | 473.2 MB | Arka plan kullanıcı uygulaması |
| **Tarayıcılar (`chrome.exe` + `msedge.exe`)** | 18 | **160.4 MB (`0.16 GB`)** | 521.9 MB | Arka plan tarayıcı süreçleri |

**Sonuç:** Sistemdeki `~6.87–7.14 GB` RAM kullanımının **yalnızca `0.2 MB` özel belleği (`15.3 MB` RSS) Quartz'a (`QuartzDesktopMCP.exe`) aittir**. Belleğin neredeyse tamamı (`~5.08 GB` süreç özel belleği + `~1.8 GB` Windows çekirdek/paylaşılan bellek) sistemde aynı anda açık olan üç yapay zeka geliştirme aracına (`claude.exe` `0.88 GB`, `ChatGPT.exe/codex` `0.86 GB`, `Antigravity.exe/language_server` `0.67 GB`), Windows sistem servislerine (`1.37 GB`) ve `Steam`/`Notion`/`Chrome` (`0.73 GB`) uygulamalarına aittir.
