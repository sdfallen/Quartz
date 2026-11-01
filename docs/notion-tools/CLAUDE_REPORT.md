# Claude teslimi: Notion araç durumu (ana sohbet)

- **Branch:** `claude/notion-tools-ui`
- **Başlangıç:** `451571251a9425a1bf32e757dd92ac74d5c6913b` (`codex/modern-ui-notion`)
- **Sözleşme:** `docs/notion-tools/PLAN.md` (yerel `notion_tools` alanı) ve `CLAUDE_PROMPT.md`
- **Durum:** UI hazır ve testli. Backend alanı ile `gui.py` çağrısı yok, bu yüzden
  gerçek sohbette henüz **görünmez**; bu beklenen davranış (alan yoksa bugünkü sohbet).

## Ne yapıldı

`ui/document.py` doküman başına (`DOCUMENT_HEAD`) küçük bir renderer ekler:
`window.QuartzNotionTools = {version: 1, update(payload, context), reset()}`.

- Panel `#notionToolsPanel`, ilk `update` çağrısında `#desktopTaskBar`'ın hemen
  altına bağlanır. Ana sohbetin içindedir, ayrı bir görev ekranı yoktur.
- **Yalnız gösterir.** pywebview API'sine erişmez, onay vermez, durdurmaz.
  Panelde düğme yoktur:
  - Onay ve ret mevcut izin kartında kalır; çift onay yüzeyi oluşmaz.
  - Durdur mevcut görev şeridinde kalır. Panel yalnız onu işaret eder. Stop yolu
    görünmüyorsa bunu açıkça yazar: "durdurma yolu görünmüyor; yeni işlem
    başlatılmaz".
- Tüm metin `textContent` ile yazılır. Kaynakta `innerHTML`, `eval`, `pywebview`,
  `.click(`, `fetch` yoktur; bunu bir test kontrol ediyor.
- Ayrı `<script id="quartz-notion-tools">` etiketi kullanıldı. `gui.py`'nin
  `<script>` bloğu ve `check_gui_javascript.py` sözleşmesi değişmedi.

### Durumlar (yalnız backend verisinden)

| Alan | Gösterim |
|---|---|
| Alan yok, `schema_version` ≠ 1, geçersiz veri | Panel gizli; bugünkü sohbet |
| `availability` ve görev yok, aktif ajan Notion değil | Panel gizli (Codex/Antigravity sohbeti etkilenmez) |
| `unavailable` | "Yerel araçlar bağlı değil" + Notion yalnız metin/kod analizi yapabilir |
| `checking` / `ready` / `blocked` | "Kontrol ediliyor" / "Hazır" + araç adları / "Engellendi" + backend mesajı |
| `observing` / `awaiting_approval` / `executing` / `verifying` | Gözlem / İzin bekleniyor (+ istenen kapsam, "izin kartından") / Yürütülüyor / Sonuç doğrulanıyor |
| `completed` + `verified` | "Tamamlandı ve doğrulandı" (yeşil); **yalnız bu kombinasyon** |
| `completed` + `observed` | "Tamamlandı · sonuç gözlendi, doğrulanmadı" |
| `completed` + `none`/eksik/bilinmeyen | "Ajan tamamlandığını bildirdi · Quartz doğrulamadı" |
| `blocked` / `failed` / `cancelled` | Engellendi / Başarısız oldu / İptal edildi |
| Bilinmeyen `state` | "Durum bilinmiyor", tahmin yapılmaz |

Model metni ("başardım, doğrulandı") başlığı veya rozeti değiştirmez.

**Operatör:** `notion` için "Yürüten: Notion", `codex`/`antigravity` için
"Yürüten: Codex · Notion bu işi devretti", tanınmayan değer (ör. `squad`) için
"Yürüten: belirtilmedi". Squad metni operatör veya yetki sayılmaz.

**Teknik ayrıntılar:** Kapalı `<details>` içinde `task_id`, `session_id`,
`revision`, `state`, `operator`, `verification`, `request.tool_name` ve
`request.scope_summary` gösterilir.

### Eski, çift ve sızan olaylar

- Yeni `task_id` geldiğinde önceki görev kalıcı olarak emekliye ayrılır. O göreve
  ait geç gelen olaylar `stale` sayılır.
- Terminal durumdaki görev (completed, blocked, failed, cancelled) yeniden aktif
  görünemez: iptal sonrası gelen `executing` yok sayılır.
- `revision` varsa eşit veya küçük revizyon `stale` sayılır. Yoksa aynı içerik
  `unchanged` döner ve DOM yeniden yazılmaz.
- `task.conversation_id` başka bir sohbete aitse panel gizlenir. `reset()` sohbet
  değişiminde görevi emekliye ayırır, böylece eski görev yeni sohbete sızmaz.

### Hareket

Panel girişi `q-fade-in` (140ms) yalnız `prefers-reduced-motion: no-preference` ve
`body:not(.low-spec)` altında çalışır. Durum değişimleri renk geçişidir; reduced
motion ve low-spec'te geçiş de kapalıdır. Stop kuralları değişmedi.

## Değişen dosyalar

- `ui/document.py`: `NOTION_TOOLS_SCRIPT`, `NOTION_TOOLS_SCRIPT_ID`, `DOCUMENT_HEAD` içinde script.
- `ui/theme.py`: `.notion-tools*` stilleri (mevcut token'lar) ve no-preference bloğunda panel girişi.
- `tests/test_notion_tools_ui.py` (yeni, 16 test).
- `docs/notion-tools/CLAUDE_REPORT.md` (bu belge).

`gui.py`, `core/`, `ui/styles.py`, spec, CI ve kullanıcı verisi değişmedi.

## Testler (gerçek sonuçlar)

Ortam: Linux konteyner, Python 3.13.18, Node 22.23.4, `requirements-dev.txt`, xvfb.
**Windows değil.**

| Komut | Baseline `4515712` | Bu dal |
|---|---|---|
| `check_python_syntax.py` | — | 220 dosya OK |
| `check_gui_javascript.py` | — | exit 0 |
| `run_safe_tests.py` | 708 koştu: 2 fail, 19 error, 17 skip | 724 koştu: 2 fail, 19 error, 17 skip |
| `audit_publish.py --staged --history` | — | findings: [] |
| `git diff --cached --check` | — | temiz |
| Hedefli: `test_notion_tools_ui`, `test_gui_modern_theme`, `test_gui_frontend_boundary`, `test_notion_frontend_integration`, `test_gui_connection_polling` | — | 52 test OK |

Fail ve error kümesi baseline ile ad ad aynı (21 test). Hepsinin nedeni Windows'a
özgü (`tkinter`, `os.startfile`, `msvcrt`, `pythoncom`).

`tests/test_notion_tools_ui.py` kapsamı:
- veri yokken uyumluluk ve sadece sohbet (Codex/Antigravity'de gizli)
- bağlanma hatası (`blocked` + mesaj)
- izin bekleme, onay sonrası yürütme, ret sonrası terminal kalma
- Stop'un yalnız mevcut şeritte kalması (panelde düğme yok, hiçbir şey tıklanmıyor)
- çift güncelleme (DOM aynı kalır), geç gelen eski görev ve eski revizyon
- sohbet değişiminde sızma yok
- `verified` yalnız backend alanından
- operatör ve devir metni
- XSS/escape (`<img onerror>`, `<script>`) ve uzunluk sınırı
- kaynakta HTML ayrıştırma ve API erişimi bulunmaması
- script'in başta ve doğru yerde olması, iki script'in birlikte `node --check`'ten geçmesi
- Codex/Antigravity yüzeyinin değişmemesi
- reduced-motion/Eco ve Stop hareket kuralları

## Ekran kanıtı ve kaynağı

**Ortam:** Linux Chromium (Playwright). Production `gui._HTML` sahte bir
pywebview API ile açıldı ve `QuartzNotionTools.update(...)` elle çağrıldı, çünkü
`gui.py` çağrısı henüz yok. Bu **mock UI kanıtıdır**; paketli Windows/WebView2
kabulü değildir.

| Mod | Panel animasyonu | Panelde düğme | 2. aynı olay | Stop tık → `desktop_task_stop` |
|---|---|---|---|---|
| Normal | `q-fade-in` | 0 | `stale` | 53 ms, 1 çağrı |
| Reduced motion | `none` | 0 | `stale` | 33 ms, 1 çağrı |
| low-spec (Eco) | `none` | 0 | `stale` | 23 ms, 1 çağrı |

Görüntüler (unavailable, checking, blocked, awaiting, executing-codex,
completed-unverified, completed-verified, failed, cancelled) repoya eklenmedi.
Yerelde `labs/claude-handoff/notion-tools-ui/` altında duruyor.

## Integration request'ler (Codex)

1. **`gui.py` çağrısı:** Aşağıdaki iki yerde çağrı eklenmeli:
   - `loadActiveConversation()`: `currentConvId` atandıktan sonra.
   - `pollUiEvents()`: `chat_status` dalında, `syncAgentUI` sonrasında.

   ```js
   window.QuartzNotionTools?.update(data.notion_tools,
     {conversationId: currentConvId, agent: mainAgentSelect?.value || conv.agent});
   ```

   Sohbet değiştiğinde (`switched`, `chat_select`, `chat_new`, silme) önce
   `window.QuartzNotionTools?.reset()` çağrılmalı.
2. **Backend `chat_status().data.notion_tools`:** PLAN şeması. Ek olarak şu
   alanlar isteniyor:
   - `task.revision`: aynı görev içinde monoton artan tamsayı.
   - `task.conversation_id`: görevin ait olduğu sohbet.
   - `task.request = {tool_name, scope_summary}`: kullanıcıya gösterilecek kısa
     özet. Yetki değildir.

   Alanlar yoksa renderer çalışır; ama revizyon koruması yerine yalnız
   task_id/terminal koruması kalır.
3. **İzin kartı (`pollNaturalTask`):** Notion araç isteği mevcut izin akışıyla
   gelecekse karta araç adı, kapsam ve "Notion istiyor; yürüten: X" satırı
   eklenmeli. Yeni API icat edilmemeli. **Karar gerekli:** Tam Yetki şu an
   warband/elevation dışındaki kapsamları otomatik onaylıyor. Bulut ajanının yan
   etkili araç isteklerinin otomatik onaylanıp onaylanmayacağı kullanıcı ve Codex
   tarafından açıkça seçilmeli. UI bunu kendisi değiştirmez.
4. **Stop:** Aktif Notion aracı yerel işlem yürütürken `desktop_task_status`
   bir `stop_ref` vermeli. Böylece mevcut "Görevi durdur" düğmesi ve HUD aynı
   görevi durdurur. Uzak işlemin durduğu doğrulanamıyorsa backend `message` ile
   bildirmeli.
5. **`scripts/check_gui_javascript.py`:** `<script id=...>` bloklarını da parse
   etmeli (şu an yalnız `gui.py` kaynağına bakıyor). Bu dalda
   `test_all_shipped_scripts_parse_together` bu açığı kapatıyor; CI betiği
   ayrıca güncellenebilir.
6. **Spec/paket:** Değişiklik gerekmez. Renderer `ui.document` Python modülünün
   içinde, `gui` import zinciriyle pakete girer.

## Kanıt seviyeleri

| Seviye | Durum |
|---|---|
| SOURCE/STATIC | ✅ |
| TESTED | ✅ Linux (yukarıdaki sonuçlar). Windows CI PR'da koşacak |
| BUILT | ❌ NOT BUILT |
| LIVE VERIFIED | ⛔ **BLOCKED**: (a) `gui.py` çağrısı yok, (b) backend `notion_tools` üretmiyor, (c) Claude'un paketli Windows oturumuna erişimi yok |

### Canlı kabul için yeniden üretim adımları (entegrasyon sonrası)

1. 1 ve 2 numaralı istekler uygulanmış paketi izole veri klasörüyle açın.
2. Notion'ı seçin. Araç bağlantısı yokken panelde "Yerel araçlar bağlı değil"
   görünmeli ve normal mesaj gönderimi bugünkü gibi çalışmalı.
3. Disposable projede salt okunur bir araç isteği tetikleyin. Panelde "İzin
   bekleniyor" ve kapsam, izin kartında aynı kapsam görünmeli.
4. Kartı **reddedin**: panel "İptal edildi" olmalı ve sonraki olaylarla yeniden
   "Yürütülüyor"a dönmemeli.
5. Yeniden tetikleyip onaylayın: Yürütülüyor → Sonuç doğrulanıyor →
   backend `verified` vermedikçe "Quartz doğrulamadı".
6. Yürütme sırasında görev şeridindeki "Görevi durdur"a basın. Tek
   `desktop_task_stop` çağrısı gitmeli ve yeni yerel işlem başlamamalı.
7. Sohbet değiştirin: eski görev yeni sohbette görünmemeli.
8. Windows "Animasyon efektleri"ni kapatıp 2. ve 6. adımları tekrarlayın.

## Geri alma

`git revert` bu dalın commit'i. Başka dosyaya bağımlılık yok; `gui.py` çağrısı
`?.` ile yazıldığı için renderer olmadan da güvenle no-op olur.
