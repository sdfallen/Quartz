# Integration Request: S4 — Fikstür Projelerinde Squad Bağlantısı ve Öz-Onarım (10 Kasım 2026)

Hazırlayan: Antigravity (Gemini)
Dal: `antigravity/wave0-wave1-analysis-20261105`
Hedef Sahipler: Codex (`core/multi_agent_service.py`, `core/natural_desktop.py`, `scripts/exam_live.py`), Claude (bilgi/doğrulama)

---

## 1. S4 Kök Neden Analizi (`LIVE` Kanıtlarla)

9 Kasım canlı sınav koşularındaki yerel kanıtlar (`dist\Quartz\quartz_projects.json`, `dist\Quartz\quartz_conversations.json`, `dist\Quartz\.quartz\run_evidence.json`, `C:\QuartzExam\fixtures\*`) incelendiğinde **üç ayrı kök neden** tespit edildi:

### Kök Neden A — Yeniden Hazırlanan (`exam_live.py prepare`) Fikstürde `.squad` Klasörünün Silinmesi (`exam-code-03` & `exam-desk-03`)
1. `exam-code-03` (`C:\QuartzExam\fixtures\exam-code-03`) ilk hazırlandığında `add_project` (`core/multi_agent_service.py:230-235`) ile Quartz'a eklendi (`id="f83adeefce95"`). İlk turda (`CONV: 91c43dacf2f54d40b7ce44ad56543d3e`) `squad.initialize()` çalıştığı için `SQUAD_CONN: True` idi.
2. Ancak `python -B scripts/exam_live.py prepare exam-code-03` ikinci ve üçüncü kez çalıştırıldığında, `scripts/exam_live.py:173` (`shutil.rmtree(fixture)`) `C:\QuartzExam\fixtures\exam-code-03\.squad` klasörünü sildi ve fikstürü `.squad` olmadan yeniden oluşturdu.
3. Proje `quartz_projects.json` içinde zaten kayıtlı ve seçili olduğundan `add_project` bir daha çağrılmadı:
   - `MultiAgentService.check_squad_connection` (`core/multi_agent_service.py:409-419`) `not st.get("initialized")` görünce `initialize()` çağırmak yerine `"Squad çalışma alanı hazır değil."` hatasını 30 sn önbelleğe aldı (`CONV: a7d2deb401594b289bd1453950c9e81e` ve `28d164e88f8540b0b30efbbd7082658d`).
   - Seçili proje hâlâ `exam-code-03` iken masaüstü görevi (`exam-desk-03`, `CONV: 12b50a08eef5460b90078e168f0cecdf`) gönderildiğinde `NaturalDesktopService.start` (`core/natural_desktop.py:397-399`) `if not self.squad.initialized: raise RuntimeError("Seçili projenin mevcut Squad bağlantısı hazır değil")` ile görevi reddetti.

### Kök Neden B — Ajan Kabuk Komutunun `.squad\messages.db` Dosyasını CRLF Metin Olarak Bozması (`exam-code-07`)
1. `C:\QuartzExam\fixtures\exam-code-07\.squad\messages.db` dosyası incelendiğinde boyutunun `28672` bayt (`7 * 4096` SQLite sayfa boyutu) yerine **`28723` bayt** olduğu ve içinde `50` adet `\r\n` (CRLF) bulunduğu, `squad agents` çağrısının ise şu hatayı verdiği doğrulandı:
   `Error: database disk image is malformed (Caused by: Error code 11: The database disk image is malformed)`
2. `dist\Quartz\.quartz\run_evidence.json` (`RUN: 6c4eed0b7dca4f949080ed294329e64b`, `seq: 2`) kaydında yazıcı ajanın şu komutu çalıştırdığı görüldü:
   ```powershell
   Get-ChildItem -Recurse -File | ForEach-Object { (Get-Content $_.FullName) -replace '\bold_name\b', 'new_name' | Set-Content $_.FullName }
   ```
   Windows'ta `git init` `.git` klasörüne `FILE_ATTRIBUTE_HIDDEN` (`0x02`) verdiği için PowerShell `Get-ChildItem -Recurse -File` `.git`'i atladı; fakat `squad.exe init` `.squad` klasörünü gizli öznitelik olmadan oluşturduğu için komut `.squad\messages.db` ikili (binary) dosyasını metin olarak okuyup CRLF ile geri yazarak SQLite veritabanını bozdu.
3. Bozulma sonrasında `(squad_root / "messages.db").is_file()` `True` kaldığı için `SquadAdapter.initialized` ve `SquadAdapter.status()` `True` döndürmeye devam etti, `initialize()` erken döndü ve proje kalıcı olarak `"Squad: Bağlantı Sorunu"` durumunda kaldı.

### Kök Neden C — `squad.exe init` Çağrısının Proje Köküne `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` Yazması
1. `squad.exe init` çalıştığında proje kökünde `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` dosyalarını oluşturuyor veya değiştiriyor (`C:\QuartzExam\fixtures\exam-code-01`, `02`, `04`, `05`, `06`, `07`, `08`, `09`, `10` içinde doğrulandı).
2. Bu dosyalar hem `changed_workspace_files` kanıtını kirletiyor (`exam-code-07` kanıtında 4 dosya değişmiş göründü) hem de ajanlara `Run squad help for all commands` talimatı vererek Quartz'ın `Kendi alt kabuğundan 'squad' komutu çalıştırma` kuralıyla çelişiyor.
3. Ayrıca `squad.exe init` tek başına yalnız `.squad/roles` ve `.squad/teams` oluşturuyor; ilk DB sorgusu (`squad agents`) çalışana kadar `.squad/messages.db` oluşmuyor.

---

## 2. Gemini Alanında (`core/squad_adapter.py`, `core/environment_health.py`) Yapılan Düzeltmeler

1. **SQLite Bozulma Tespiti ve Öz-Onarım (`core/squad_adapter.py`):**
   - `SquadAdapter._is_db_corrupt(db_path)`: `>= 100` baytlık gerçek `messages.db` dosyalarında SQLite başlığını (`SQLite format 3\x00`) ve salt-okunur `PRAGMA quick_check(1)` sonucunu kontrol eder. Bozuksa `True` döner.
   - `SquadAdapter.initialized`: `messages.db` bozuksa `False` döner.
   - `SquadAdapter.status()` ve `SquadAdapter._run()`: `.squad` klasörü mevcutken `messages.db` bozuksa veya `squad.exe` `database disk image is malformed` / `file is not a database` / `no such table` hatası döndürürse `_repair_workspace()` ile bozuk DB dosyalarını silip `.squad` çalışma alanını yerinde yeniden kurar ve komutu tekrar dener.
2. **Kök Klasörü Kirletmeyen ve Gizli (`.squad` `FILE_ATTRIBUTE_HIDDEN`) Başlatma (`core/squad_adapter.py`):**
   - `initialize()` ve `_repair_workspace()` çalışırken proje kökündeki `(".gitignore", "AGENTS.md", "CLAUDE.md", "GEMINI.md")` dosyalarının önceki durumu kaydedilir ve `squad init` sonrasında birebir geri yüklenir (önceden olmayanlar silinir).
   - Proje bir Git deposuysa (`.git/info` varsa), `.squad/` satırı `.git/info/exclude` içine eklenir; böylece çalışma ağacı kirlenmeden Git `.squad/` klasörünü yoksayar.
   - Windows'ta `.squad` klasörüne `FILE_ATTRIBUTE_HIDDEN` (`0x02`) verilir; böylece PowerShell `Get-ChildItem -Recurse -File` tıpkı `.git` gibi `.squad` klasörünü de varsayılan olarak atlar.
   - `initialize()` sonunda `messages.db` henüz oluşmamışsa `squad agents --json` çalıştırılarak `.squad/messages.db` dosyasının hemen oluşması garanti edilir.
3. **`core/environment_health.py` (P3 + Bozuk DB Kontrolü):**
   - `_selected_agents("notion")` artık boş küme (`set()`) döner; `notion` modunda `codex_cli` ve `antigravity_cli` gereksiz `blocked` olmaz.
   - `_run_subprocess` `(OSError, ValueError, TypeError)` yakalar ve `_probe_squad_fallback` bozuk `messages.db` dosyasını `SquadAdapter._is_db_corrupt` ile tespit eder.

---

## 3. Codex Alanı İçin İstenen Küçük Entegrasyon Değişiklikleri

`exam-code-03` gibi **kayıtlı bir projenin klasörü yeniden oluşturulduğunda (`exam_live.py prepare`)** `.squad` klasörü tamamen silindiği için (ve `tests/test_warband_squad_status.py` ile `tests/test_squad_idle_cache.py` boşta `status()` çağrısının başlatılmamış klasörde otomatik `init` yapmamasını şart koştuğu için), görev başlatma / bağlantı doğrulama noktalarında şu 3 küçük dokunuş önerilir:

1. **`core/multi_agent_service.py` — `check_squad_connection` (satır ~409):**
   - Kayıtlı ve `workflow != "warband"` olan bir projede `check_squad_connection` çağrıldığında `not st.get("initialized")` ise (ör. `exam_live.py prepare` klasörü sıfırladıysa), `squad.initialize()` çağrılıp `st = squad.status()` yenilenmeli:
   ```python
   st = squad.status()
   if st.get("installed") and not st.get("initialized"):
       try:
           squad.initialize()
           st = squad.status()
       except Exception as exc:
           st["error"] = str(exc)
   ```
   *(Not: Mevcut hiçbir test `check_squad_connection`'ın `initialize()` çağırmamasını şart koşmuyor; `test_warband_squad_status.py:29` yalnız `workflow == 'warband'` için `squad.initialize.assert_not_called()` kontrol ediyor ve `warband` satır 407'de erken dönüyor.)*

2. **`core/natural_desktop.py` — `NaturalDesktopTask.start` (satır ~397-399):**
   - Seçili proje `warband` değilken masaüstü görevi başladığında `self.squad.initialized` `False` ise reddetmeden önce `self.squad.initialize()` denenmeli:
   ```python
   else:
       self.squad = self.squad_factory(str(root))
       if not self.squad.initialized:
           self.squad.initialize()
   if not self.squad.initialized:
       raise RuntimeError("Seçili projenin mevcut Squad bağlantısı hazır değil")
   ```

3. **`scripts/exam_live.py` — `prepare` (satır ~190):**
   - `setup.get("project")` `True` olan görevlerde `prepare()` fikstürü sıfırladıktan sonra `SquadAdapter(fixture).initialize()` çağırırsa (ve `baseline = exam_oracle.snapshot(fixture)` öncesinde `.squad` hazır olursa), Quartz açıkken fikstür sıfırlansa bile `.squad/messages.db` ve `.git/info/exclude` baştan hazır olur.

---

## 4. Bağımsız İnceleme: `claude/health-card-20261109` (`8de3b0f`) ve `claude/health-card-pending-20261110` (`05ab9aa`, `0bec8da`)

- **İncelenen commit'ler:**
  - `8de3b0fe4e2aa41e23e5324478e9e7ffc946f4d6` (`claude/health-card-20261109`)
  - `05ab9aaf26818cc69f69f4c7bc56cb0675490a5d`, `0bec8da53eae625852b0ba93fc50e21fbd971e3b` (`claude/health-card-pending-20261110`)
- **Değişen dosyalar (Claude sahipliğinde):**
  - `assets/workspace.css`, `gui.py`, `ui/shell.py`, `ui/js_chat.py`, `tests/test_environment_health_card.py`, `docs/CLAUDE_REVIEW_HEALTH_INTEGRATION_20261110.md`
- **Karar:** **ACCEPT** (`SOURCE` + `TESTED`). Engelleyici bulgu yok (`0` bulgu).
- **Teknik Değerlendirme:**
  1. `renderEnvironmentHealth(result)` yalnız arka uçtan gelen `status` ve `checks` dizisini gösterir; kendi başına `ok/warn/blocked` kararı vermez.
  2. `diagnostics.age_seconds == null` yer tutucu (`"Ortam kontrol ediliyor."`) geldiğinde `error` yoksa mevcut görünümü korur (sahte sarı uyarı üretmez); yükleyici hata verdiyse `"Ortam kontrolü yapılamadı."` uyarısını gösterir.
  3. Tüm metinler (`summary_tr`, `fix_tr`, `detail`) `textContent` ile DOM'a yazılır (`innerHTML` yok, XSS güvenli).
  4. `gui.Api.environment_health(force=False)` yalnız `force is True` olduğunda zorlamalı kontrol iletir.

---

## 5. Doğrulama Komutları ve Birebir Çıktıları (`TESTED` + `LIVE`)

### 5.1 Gerçek Bozuk `exam-code-07/.squad` Kopyası Üzerinde Öz-Onarım Testi

Komut:
```powershell
Set-Location "C:\Users\LENAVO\.gemini\antigravity\worktrees\quartz-wave0-wave1-20261105"; python -B -c "import shutil, tempfile, pathlib; from core.squad_adapter import SquadAdapter;
src = pathlib.Path(r'C:\QuartzExam\fixtures\exam-code-07\.squad')
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d)
    shutil.copytree(src, p / '.squad')
    ad = SquadAdapter(p)
    print('BEFORE repair -> _is_db_corrupt:', SquadAdapter._is_db_corrupt(p / '.squad' / 'messages.db'), 'initialized:', ad.initialized)
    agents = ad.agents()
    st = ad.status()
    print('AFTER ad.agents() -> _is_db_corrupt:', SquadAdapter._is_db_corrupt(p / '.squad' / 'messages.db'), 'initialized:', ad.initialized, 'status.initialized:', st['initialized'], 'agents_count:', len(agents))
    print('ROOT pollution files created:', [f.name for f in p.iterdir() if f.name != '.squad'])
"
```

Çıktı:
```text
BEFORE repair -> _is_db_corrupt: True initialized: False
AFTER ad.agents() -> _is_db_corrupt: False initialized: True status.initialized: True agents_count: 0
ROOT pollution files created: []
```

### 5.2 Birim ve Entegrasyon Testleri (`58` Test)

Komut:
```powershell
Set-Location "C:\Users\LENAVO\.gemini\antigravity\worktrees\quartz-wave0-wave1-20261105"; python scripts/check_python_syntax.py; python -B -m unittest tests.test_squad_adapter tests.test_environment_health tests.test_squad_idle_cache tests.test_warband_squad_status tests.test_project_ipc tests.test_chat_coordination -v
```

Çıktı:
```text
Published Python syntax: 344 files OK
Ran 58 tests in 13.593s

OK
```
