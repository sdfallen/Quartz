# Quartz piramidi — Katman 5 sunum sınırı (Claude)

Sahip: Claude. Dal: `claude/pyramid-frontend`.
Baseline: `047fa6e` (`codex/architecture-pyramid-20261101`, P0). Tree `126f0e7`,
kullanıcının `quartz-architecture` worktree index'iyle `git write-tree` üzerinden
eşleşti. Kaynak davranışı PYRAMID.md'ye göre `e2ce872` ile aynı.
Güncel sözleşme: `docs/architecture/PYRAMID.md` ve `TEAM.md`.
`docs/CLAUDE_FRONTEND_ARCHITECTURE.md` tarihseldir. Dilim 1'in önceki planı orada,
bu belge onun yerine geçer.

Kanıt seviyesi: **SOURCE + TESTED (Linux)**. BUILT ve LIVE VERIFIED **yok**.
Paket kurulmadı, Windows/WebView2'de açılmadı, kullanıcı EXE'sine dokunulmadı.
Linux'ta Python/Node testleri ve mock karşılaştırma bir Windows GUI kabulü değildir.

## 1. Sınır haritası: `gui.py` bugün neyi taşıyor?

`gui.py` baseline'da 3.920 satır, bu dilimden sonra 3.604. Üst seviye import'u yalnız `webview`, `core.local_ipc.request_token`
ve `ui.*`. Diğer 14 `core` bağımlılığı metot içinde lazy import ediliyor.
Aşağıdaki tablo, her durumun asıl kaynağını (otorite) ve hangi katmana ait
olması gerektiğini gösteriyor. Kaynak: `gui.py@047fa6e` AST + okuma. Runtime trace değildir.

| `Api` grubu | GUI sürecinde ne yapıyor | Durumun asıl kaynağı | Katman | Bulgu |
|---|---|---|---|---|
| `chat_*`, `project_select`, `chat_poll`, `chat_cancel`, `chat_models`, `chat_set_model` | Saf IPC vekili (`ipc_send`) | Backend `agent_chat` + `conversation_store`. Model tercihi sohbet başına backend'de tutulur. JS'de localStorage yok | 5 (doğru) | — |
| `project_pick_add` | Native klasör seçici → seçilen yol `project_add` ile gönderilir | Kullanıcının native seçimi, kayıt backend `project_registry`'de | 5 (picker) | Güvenilir GUI girişi. Yol, JS'den değil, dialog'dan gelir |
| `onboarding_status/begin` | `OnboardingService` GUI sürecinde kuruluyor | `core.onboarding` (GUI süreci). `onboarding_refresh` ise backend'de | 5'te 1/3 işi | Aynı alan iki süreçte. Otorite belirsiz |
| `diagnostics_select_application` | Native `.exe` seçici → GUI'de `ArtifactDiagnosticsService(selected[0])` kurulup başlatılıyor | GUI-yerel `self._artifact_diagnostics`. Yoksa backend `diagnostics_*` | Picker 5. Servis yaşam döngüsü 4/3 | PYRAMID'deki "UI ile iş yaşam döngüsü iç içe" bulgusu. İş durumu iki süreçte: `diagnostics_status` önce GUI'ye, sonra backend'e bakıyor |
| `diagnostics_prepare/apply/discard_repair` | Native klasör seçici → GUI'de `PackageRepair(app_root(), LOCALAPPDATA/…)` | GUI-yerel `self._repair` (plan) | Picker 5. Onarım 3 | Yedek yolu GUI'de hesaplanıyor |
| `diagnostics_learned_applications` | `ApplicationKnowledge().list_learned(20)` GUI'de | `core.application_knowledge` kalıcı kaydı | 3/1 | Salt okuma |
| `natural_start/status/approve/deny` | Önkoşulları backend `chat_status`'tan okuyor, GUI'de `NaturalDesktopTask` kuruyor, sohbete IPC ile yazıyor, seçili ajana göre metne `Codex, ` / `Gemini, ` öneki ekliyor | Görev GUI-yerel `self._natural`. Sohbet günlüğü backend | 4 | İş kuralı (ajan öneki, bağlam kırpma 8 mesaj/10.000 karakter) L5'te. İzin onayı aynı canlı görevin `request_id`'sine bağlı |
| `coordination_route` | Niyet yönlendirme (`message_intent`, `diagnostics_intent`, `desktop_intent`, `proposed_roles`), "yetkiler" ve "devam" sorularına sabit yanıt, metinle Stop | GUI-yerel `_natural`/`_coordination` + backend `chat_status` | 4 | En büyük L4 sızıntısı (136 satır). Proje `workflow=="warband"` dalı tarihsel. ASTER kapsam dışı, dokunulmadı |
| `coordination_prepare/approve/pick_app/pick_log/stop` | GUI'de `ChatCoordination` kuruyor. Native `.exe`/log seçicileri | GUI-yerel `self._coordination` | Picker 5. Görev 4 | Picker'lar güvenilir giriş. Plan/onay GUI-yerel |
| `desktop_task_status/stop` | GUI-yerel servislerden `desktop_view` türetip `stop_ref` üretiyor | GUI-yerel `_natural`/`_coordination` | 5 (görünüm) + 4 (Stop yönlendirme) | Stop yetkisi GUI sürecindeki servistedir |
| `desktop_operator_*` | GUI'de `DesktopAgentService` | GUI-yerel `_desktop_agents` | 3 | — |
| `get_stats` | `psutil` + `low_spec_optimizer` GUI'de, arka plan bakım iş parçacığı | GUI süreci | 1 | — |
| `cleanup_before_exit` | Yerel servisleri durdurup `ipc_send("shutdown")` | GUI + backend | 4 | PYRAMID "kapanış birden fazla yerde" bulgusu |
| `voice_*`, `push_to_talk`, `toggle_wake_word` | GUI'de `VoiceSystem` | GUI süreci | Legacy uyumluluk | Dokunulmadı |
| `minimize`, `set_compact`, `close` | Pencere | pywebview | 5 (doğru) | — |
| `notion_tool_decide` + `@notion` korumaları | IPC vekili. Notion mesajı yerel araç başlatmaz | Backend | Askıda | UI'da düğme yok (test korur). Codex'in alanı, dokunulmadı |
| `_HTML`: baş, CSS, gövde, JS | Belge birleştirme | `ui/document.py`, `ui/styles.py`, `ui/theme.py`, **`ui/shell.py` (yeni)**, JS `gui.py` | 5 | JS ~2.640 satır (915–3555) hâlâ `gui.py`'de |

Sonuç: `gui.py` 4. ve 3. katman işlerini (doğal görev, koordinasyon, teşhis/onarım servisi)
GUI süreci içinde kuruyor ve bu görevlerin otoritesi GUI sürecinde. Bu bir sunum
temizliğiyle düzeltilemez. Servis sahipliği P1 (Codex) sözleşmesine bağlı
(Bölüm 6 IR-3). Native picker → servis kurulumu çizgisi korunmalı: seçimi
yalnız dialog üretir. IPC'den gelen keyfî yol izin üretmez.

## 2. Seçilen dilim: gövde işaretlemesi → `ui/shell.py`

Neden bu dilim:
- Davranış içermiyor: 317 satır, 112 id, inline `on*=` handler yok,
  `pywebview.api` çağrısı yok, script yok.
- JS kontrolünü etkilemiyor, çünkü JS `gui.py`'de kalıyor. Ship-ready
  için Codex entegrasyonuna bağlı değil.
- Servis/izin/Stop koduna dokunmuyor.

Değişiklik (`git diff 047fa6e`):
- `ui/shell.py` (yeni): `SHELL_MARKUP` = eski `_HTML_BODY`'nin `</head>`'ten
  açılış script etiketine kadar olan kısmı, bayt bayt aynı.
- `gui.py`: `from ui.shell import SHELL_MARKUP` (üst seviye, statik).
  `_HTML_BODY = SHELL_MARKUP + r"""<script>…`. Yorum güncellendi.
  Başka satır değişmedi.
- `tests/test_gui_frontend_boundary.py`: `ShellMarkupBoundaryTests` (5 test).

Değişmeyenler: `gui._HTML`, `gui._HTML_BODY`, `_ASSET_ROOT`, `_BRAND_MARK`, `Api`
(metot adları ve gövdeleri), `QuartzUI`, `workspace.css`, tema, reduced motion,
Q markası. Mesaj akışı, partial response, sohbet değişimi, model tercihleri,
izin kartı ve Stop aynı JS ile aynı DOM üzerinde çalışıyor.

Bayt eşitliği (Linux, kaynak modu):

| | Uzunluk (karakter) | SHA-256 |
|---|---|---|
| `gui._HTML` önce/sonra | 225.966 / 225.966 | `db61e6fb…95bd02` / aynı |
| `gui._HTML_BODY` önce/sonra | 147.394 / 147.394 | `35a398d5…d06fc` / aynı |

Belge bayt bayt aynı olduğu için tarayıcı render karşılaştırması ek bilgi
vermez ve yapılmadı. Frozen (`_MEIPASS`) yolu yalnız asset kökünü değiştirir.
Bu, mevcut `test_frozen_bundle_root_is_used_for_assets` ile kapsanıyor.

## 3. Sözleşme testleri (`ShellMarkupBoundaryTests`)

1. `_HTML_BODY` = `SHELL_MARKUP` + `gui.py` kaynağındaki tek script bloğu.
   Kaynakta tam **1** script bloğu olmalı ve 1.000 karakterden büyük olmalı.
   Böylece boş eşleşme başarı sayılmaz.
2. Shell yalnız sunum taşır: script yok, `pywebview.api` yok, inline handler yok,
   Python import'u yok, `notion` yok.
3. Sohbet, gönder, iptal, üç Stop düğmesi, HUD, yetki seçimi ve iki model seçicisi
   id'leri var. Tekrarlanan id yok. Marka placeholder'ı yerinde.
4. JS'in `getElementById('…')` ile aradığı 102 literal id'nin hepsi belgede var
   veya JS tarafından oluşturuluyor.
5. `gui.py` `ui.shell`'i statik `ImportFrom` ile alıyor (PyInstaller analizi).

Mutasyon kontrolü (geçici, geri alındı):
- Shell'de `btnCancel` id'si değiştirilince 2 test düştü.
- Script etiketi `<script >` yapılınca 2 test düştü.

## 4. Koşulan kontroller (bu ortam: Linux, Python 3.13, Node)

| Kontrol | Sonuç |
|---|---|
| Hedefli: `test_gui_frontend_boundary`, `test_gui_modern_theme`, `test_chat_keyboard`, `test_gui_compact`, `test_gui_connection_polling`, `test_notion_frontend_integration` | Baseline'da 46 test OK. Boundary dosyası değişiklikten sonra 18 test OK |
| `check_python_syntax.py` | 235 dosya OK |
| `check_gui_javascript.py` | exit 0 (Bölüm 5'teki uyarıyla) |
| `run_safe_tests.py` | Sonra: 818 test, 2 fail + 19 error, 17 skip. Baseline `047fa6e`: 813 test, aynı 2+19 |
| `audit_publish.py --staged --history` | PASS, 0 bulgu (369 dosya, 570 history blob) |
| `git diff --cached --check` | Temiz |

`run_safe_tests` farkı: başarısız/hatalı test kimlik listeleri baseline ile
**birebir aynı** (`diff` boş). Hepsi bu Linux ortamından kaynaklanıyor:
`pyautogui` gibi Windows modülleri eksik, `codex.cmd`/`node.exe` yol çözümü,
Windows'a özgü UAC ve native testler. +5 test bu dilimin yeni testleri.
Windows'ta tam suite koşulmadı.

## 5. Engeller ve açık konular

- **BUILT/LIVE yok.** Bu oturumda Windows'ta komut çalıştırma ve PyInstaller
  build yapma imkânı yoktu. İzole paketli GUI kontrolü yapılmadı.
- **JS kontrolü boş girdiyle geçiyor (doğrulandı).** `gui.py`'deki script etiketi
  eşleşmediğinde de `check_gui_javascript.py` exit 0 verdi, çünkü yalnız
  `NOTION_TOOLS_SCRIPT` parse edildi. Bu dilim JS'i taşımıyor. Bölüm 3'teki
  test 1, `gui.py` için bu açığı test suite içinde kapatıyor. Ama betiğin
  kendisi hâlâ zayıf (IR-1).
- `docs/PARALLEL_OWNERSHIP.md` eski Notion kapsamını gösteriyor. Aktif sahiplik
  TEAM.md. Dosya Codex'in, dokunulmadı.

## 6. Integration request'ler (Codex)

**IR-1 — `scripts/check_gui_javascript.py` boş girdiyi başarı saymasın (JS taşınmadan önce şart).**
- Neden: Bölüm 5'teki mutasyon, `gui.py` bloğu eşleşmese de exit 0 alındığını gösterdi.
- Öneri: Doğrulamayı ham kaynaktan değil, sevk edilen belgeden yap
  (`from gui import _HTML` yerine `ui.document.build_document` +
  `ui.shell`/gelecek JS modülü), ya da en azından:
  ```python
  scripts = re.findall(r"<script>(.*?)</script>", source, re.S)
  if len(scripts) != 1 or len(scripts[0].strip()) < 1000:
      print("gui.py application script block missing"); raise SystemExit(2)
  ```
- Test: Script etiketini bozan bir fixture ile non-zero exit.
- Bu yapılmadan **JS dilimi (dilim 2) başlatılmayacak.**

**IR-2 — `Quartz.spec` hiddenimports'a `'ui.shell'` ekle.**
- Neden: Spec, `ui.document/styles/theme`'yi açıkça listeliyor. `ui.shell`,
  `gui`'nin statik import'uyla da bulunur, ama liste tutarlı kalsın.
  Eksik modül paketli uygulamada açılışta `ImportError` verir.
- Test: Build sonrası `verify_desktop_package.py` + EXE'nin izole bir kopyasını
  açıp ana sohbetin yüklendiğini görmek (kullanıcı EXE'si değil).
- **Codex bu build + izole açılış kontrolünü yapana kadar dilim ship-ready ilan edilmez.**

**IR-3 — GUI sürecindeki görev/servis otoritesi (P1 girdisi, kod isteği değil).**
- `natural_start`/`coordination_route`/`coordination_prepare`/`diagnostics_*`
  GUI sürecinde `NaturalDesktopTask`, `ChatCoordination`, `ArtifactDiagnosticsService`,
  `PackageRepair`, `OnboardingService` kuruyor. Görev durumu ve Stop otoritesi GUI sürecinde.
- Önerilen sözleşme: GUI yalnız (a) kullanıcı metni + sohbet/proje kimliği,
  (b) native picker sonucu, (c) onay/ret/Stop olayını iletir. Servis kurulumu,
  niyet yönlendirme ve ajan öneki uygulama katmanında olur. Picker sonucu
  "seçim yapıldı" olarak bu süreçten üretilmeye devam eder. IPC'ye keyfî yol
  kabul eden yeni bir uç açılmaz.
- Claude'un payı: Codex sözleşmeyi sabitledikten sonra `Api` metotlarını aynı
  adlarla ince vekile çevirmek. O zamana kadar bu metotlara dokunulmaz.

## 7. Geri alma

Tek commit. Davranış farkı yok, veri/şema değişmedi:
```
git revert <bu commit>
```
Ya da elle: `gui.py`'de `SHELL_MARKUP + r"""<script>` kısmını `ui/shell.py`'deki
metinle değiştirip import'u kaldır, `ui/shell.py`'yi ve `ShellMarkupBoundaryTests`'i
sil. `gui._HTML` SHA-256'sı `db61e6fb…95bd02`'ye dönmeli. Kullanıcı verisi,
sohbet geçmişi ve kurulu EXE bu dilimden etkilenmez.

## 8. Sonraki dilim (bu teslimde yapılmadı)

Dilim 2: Uygulama JS'ini bölümlere ayırma. Ön koşullar: IR-1 ve IR-2 entegre
edilmiş olmalı, ayrıca bu dilim Windows'ta build ve izole açılış ile doğrulanmalı.
Tek dilim doğrulanmadan ikinci refactor başlatılmayacak.
