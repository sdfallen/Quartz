# Integration Request: S4 — Fikstür Projelerinde Squad Bağlantısı ve Güvenli Karantina/Onarım (10 Kasım 2026)

Hazırlayan: Antigravity (Gemini)
Dal: `antigravity/wave0-wave1-analysis-20261105`
Hedef Sahipler: Codex (`core/multi_agent_service.py`, `core/natural_desktop.py`, `scripts/exam_live.py`), Claude (inceleme: `docs/CLAUDE_REVIEW_S4_SQUAD_20261110.md`)

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

## 2. Gemini Alanında (`core/squad_adapter.py`, `core/environment_health.py`) Yapılan Düzeltmeler (Claude `3ebd96f` P1/P2 İncelemesi Sonrası)

1. **Yalnız Olumlu Kanıtla Bozulma Tespiti (`SquadAdapter._is_db_corrupt`):**
   - Yalnız iki olumlu kanıt durumunda `True` döner:
     1. `>= 100` baytlık dosyanın ilk 16 baytı `b"SQLite format 3\x00"` değilse, veya
     2. `PRAGMA quick_check(1)` sonucu `"ok"` dışında bir satır döndürürse ya da `sqlite3.DatabaseError` mesajı açıkça bozulma kanıtı (`database disk image is malformed`, `file is not a database`, `not a database file`) içeriyorsa.
   - `sqlite3.OperationalError` (`database is locked`, `unable to open database file`, meşgul/kilitli durum) ve `OSError` **asla bozuk sayılmaz (`False` döner)**.
   - `"no such table"` bozulma belirteçleri listesinden çıkarıldı.
2. **Silme Yok — Zaman Damgalı Karantinaya Taşıma (`_quarantine_corrupt_db_files`):**
   - Bozuk `messages.db` (ve varsa `-wal` / `-shm`) **asla silinmez** (`unlink` yok); `messages.db.corrupt-<YYYYMMDD-HHMMSS>` olarak aynı klasörde karantinaya taşınır (`Path.replace`).
   - Dış bir süreç dosyayı açık tutuyorsa Windows'ta `replace` `OSError` fırlatır ve onarım hiçbir dosyaya dokunmadan iptal olur. Son karantina yolu `adapter.last_quarantined_db` alanında saklanır.
3. **Salt Okunur Yollarda (`status`, `initialized`, `agents`, `tasks`, `history`, `environment_health`) Onarım Yok:**
   - `status()`, `initialized`, salt okunur komutlar (`--version`, `agents`, `task list`, `history`, `receive`) ve `environment_health` **hiçbir zaman** `_repair_workspace()` çağırmaz, dosya taşımaz veya değiştirmez.
   - `status()` bozuk DB gördüğünde salt okunur olarak `initialized: False` ve `error: "Squad veritabanı (.squad/messages.db) bozuk; yeniden başlatılmalı."` bildirir.
   - Onarım ve karantina **yalnız açık başlatma/yazma yollarında** (`initialize()`, `join()`, `leave()`, `send()`, `create_task()`, `ack_task()`, `complete_task()`, `requeue_task()`) çalışır.
4. **Cerrahi Kök Dosya Temizliği ve Gizli `.squad` (`_restore_root_files`, `_hide_squad_dir`):**
   - `squad init` öncesinde var olmayan `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` dosyaları yalnız Squad şablonu içeriyorsa silinir; önceden var olan dosyalarda ise yalnız `squad init` tarafından eklenen Squad şablonu geri alınır.
   - Git depolarında `.git/info/exclude` içine `.squad/` eklenir; Windows'ta `.squad` klasörüne `FILE_ATTRIBUTE_HIDDEN` (`0x02`) verilir.
5. **`core/environment_health.py` (P3 + Bozuk DB Kontrolü):**
   - `_selected_agents("notion")` boş küme (`set()`) döner; `_run_subprocess` `(OSError, ValueError, TypeError)` yakalar; `_probe_squad_fallback` bozuk `messages.db` dosyasını salt okunur olarak tespit eder.

---

## 3. Codex Alanı İçin İstenen Küçük Entegrasyon Değişiklikleri

1. **`core/multi_agent_service.py` — `check_squad_connection` (satır ~409):**
   - Kayıtlı ve `workflow != "warband"` olan bir projede `check_squad_connection` çağrıldığında `not st.get("initialized")` ise (ör. `exam_live.py prepare` klasörü sıfırladıysa veya `messages.db` bozulduysa), `squad.initialize()` çağrılıp `st = squad.status()` yenilenmeli:
   ```python
   st = squad.status()
   if st.get("installed") and not st.get("initialized"):
       try:
           squad.initialize()
           st = squad.status()
       except Exception as exc:
           st["error"] = str(exc)
   ```

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
   - `setup.get("project")` `True` olan görevlerde `prepare()` fikstürü sıfırladıktan sonra `SquadAdapter(fixture).initialize()` çağırırsa, Quartz açıkken fikstür sıfırlansa bile `.squad/messages.db` ve `.git/info/exclude` baştan hazır olur.

---

## 4. Bağımsız İnceleme: `claude/health-card-20261109` (`8de3b0f`) ve `claude/health-card-pending-20261110` (`05ab9aa`, `0bec8da`)

- **Karar:** **ACCEPT** (`SOURCE` + `TESTED`, `0` bulgu).

---

## 5. Doğrulama Komutları ve Birebir Çıktıları (`TESTED` + `LIVE`)

### 5.1 500 Mesajlık Kilitli DB (`BEGIN EXCLUSIVE`) ve Gerçek Bozuk `exam-code-07/.squad` Karantina Doğrulaması

Komut:
```powershell
Set-Location "C:\Users\LENAVO\.gemini\antigravity\worktrees\quartz-wave0-wave1-20261105"; python -B -c "import shutil, sqlite3, tempfile, pathlib; from core.squad_adapter import SquadAdapter;
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d)
    (p / '.squad').mkdir()
    db = p / '.squad' / 'messages.db'
    c = sqlite3.connect(str(db))
    c.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT);')
    c.executemany('INSERT INTO messages (body) VALUES (?);', [(f'm{i}',) for i in range(500)])
    c.commit(); c.close()
    ad = SquadAdapter(p)
    print('healthy, unlocked            -> _is_db_corrupt:', SquadAdapter._is_db_corrupt(db))
    w = sqlite3.connect(str(db), timeout=1.0, isolation_level=None)
    w.execute('BEGIN EXCLUSIVE;')
    print('healthy, writer holds lock   -> _is_db_corrupt:', SquadAdapter._is_db_corrupt(db))
    w.execute('ROLLBACK;'); w.close()
    st = ad.status()
    c2 = sqlite3.connect(str(db))
    cnt = c2.execute('SELECT COUNT(*) FROM messages;').fetchone()[0]
    c2.close()
    print('after lock release + status()-> messages.db exists:', db.is_file(), 'row_count:', cnt, 'initialized:', st['initialized'])

src = pathlib.Path(r'C:\QuartzExam\fixtures\exam-code-07\.squad')
with tempfile.TemporaryDirectory() as d2:
    p2 = pathlib.Path(d2)
    shutil.copytree(src, p2 / '.squad')
    ad2 = SquadAdapter(p2)
    st_before = ad2.status()
    q_before = [f.name for f in (p2 / '.squad').glob('messages.db.corrupt-*')]
    print('corrupt exam-code-07 status()-> initialized:', st_before['initialized'], 'quarantined_by_status:', q_before)
    ad2.initialize()
    q_after = [f.name for f in (p2 / '.squad').glob('messages.db.corrupt-*')]
    print('after initialize()           -> initialized:', ad2.initialized, 'quarantined_files:', q_after, 'quarantine_size:', (p2 / '.squad' / q_after[0]).stat().st_size)
"
```

Çıktı:
```text
healthy, unlocked            -> _is_db_corrupt: False
healthy, writer holds lock   -> _is_db_corrupt: False
after lock release + status()-> messages.db exists: True row_count: 500 initialized: True
corrupt exam-code-07 status()-> initialized: False quarantined_by_status: []
after initialize()           -> initialized: True quarantined_files: ['messages.db.corrupt-20261110-081104', 'messages.db.corrupt-20261110-081104-shm', 'messages.db.corrupt-20261110-081104-wal'] quarantine_size: 28723
```

### 5.2 Birim Testleri (`25` Test: `test_squad_adapter` + `test_environment_health`)

Komut:
```powershell
Set-Location "C:\Users\LENAVO\.gemini\antigravity\worktrees\quartz-wave0-wave1-20261105"; python scripts/check_python_syntax.py; python -B -m unittest tests.test_squad_adapter tests.test_environment_health -v
```

Çıktı:
```text
Published Python syntax: 344 files OK
Ran 25 tests in 3.957s

OK
```
