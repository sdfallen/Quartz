# Yanıtsız izin kartı — Dalga 2 tasarımı (uygulanmadı)

Amaç: kart beklerken görev duraklar, ajan yeni girdi göndermez. On dakika
sonra izin geçerliliği düşebilir ama görev başarısız/cancelled/completed olmaz.
Yeni motor veya otorite kaydı oluşturulmaz. İlk dilim NaturalDesktopTask'ın
desktop/log/elevation kartlarıdır; kullanıcı süreli ChatCoordination ve legacy
oyun yolu sessizce değiştirilmez. Diğer inceleme izinleri ayrı integration request.

## Dosya ve sahiplik

| Dosya | Tasarlanan küçük değişiklik |
|---|---|
| `core/natural_desktop.py` / Codex | `_request`, `approve`, `_watch`, `_provider`, `call`, `_jarvis_call`, `_assert_jarvis_generation`, `_jarvis_input_guard`, `_elevation_worker`, `stop`: aynı job/generation'a bağlı paused-awaiting-approval durumu ve tek yan etki kapısı. |
| `core/desktop_broker.py` / Claude | Pause anında mevcut grant revoke edilir; snapshot/token yenilenmez. Resume'da onaylı kapsam ve güncel target identity ile yeni session. R1 token bağlı renewal bozulmaz. |
| `core/task_outcome.py` / Codex | `paused/awaiting_approval`, cancellation veya başarı gibi anlatılmaz; goal_accepted=False korunur. |
| `gui.py`, `ui/js_desktop.py`, ilgili izin kartı JS'i / Claude | “Onay bekleniyor — görev duraklatıldı”, süresi dolan kart için açık yeniden onay akışı; Durdur erişilebilir. API request/generation kimlikleri korunur. |
| `core/atomic_json.py` | Mevcut atomik yazar kullanılır, değiştirilmez. Task evidence dizininde küçük pause checkpoint'i; token/screenshot/parola yazılmaz. |
| `tests/test_natural_desktop.py`, `tests/test_permission_continuation_ui.py`, yeni orchestration pause testleri | Aşağıdaki kabul matrisi. Broker/UI testleri sahipleriyle koordineli. |

## Durum geçişi ve yetki

1. Gerçekten kullanıcı yanıtı gerektiren kart açılırken **running →
   awaiting_approval (paused)**. Full tercihiyle mevcut kurallara göre hemen
   auto-approve olan sıradan istek yapay olarak bekletilmez. UAC buna dahil değil.
2. Pause işaretlemesi ile mevcut input grant'in iptali tek tanımlı sınırdır.
   Sadece yeni pencere değil, önceki onaylı pencerelere de girdi durur. Eski
   snapshot ve bearer geçersizleşir. `preserve_input` kart beklerken girdi
   sürdürme izni değildir. Broker lease'i paused durumda heartbeat ile yenilenmez.
3. Doğrudan MCP, Jarvis, UI callback ve queued/inflight input her yan etkiden
   hemen önce aynı job+generation+paused kontrolünü görür. Daha önce gerçekleşmiş
   etki geri alınmış gibi gösterilmez; sonucu bilinmeyen eylem tekrar edilmez.
4. Beklerken task_context/task_wait, görev mesajları ve zaten onaylı salt okunur
   loglar okunabilir. `desktop_observe` refocus yaptığı için pasif sayılmaz;
   pause sırasında focus/switch/launch/input/UAC açma otomatik yapılmaz.
5. On dakika dolunca kartın request generation'ı geçersizdir; görev aynı paused
   job olarak kalır. “İzin süresi doldu; devam için yeniden onay gerekli” gösterilir.
   Watchdog `stop('permission expired')` çağırmaz; Squad complete/finished_at/
   öğrenme finalize veya başarı receipt'i üretmez.
6. Geçerli yeni kullanıcı yanıtında task+conversation+request+generation yeniden
   doğrulanır. Expired kart için trusted UI yeni request/generation çıkarır;
   eski karta yapılan callback'in yeni yetkiye dönüşmesi yasaktır. HWND/PID/
   process start/EXE ve input desktop tekrar doğrulanır. Değişen pencere yeni
   seçim gerektirir. Fresh observation olmadan ilk input yoktur.
7. UAC onayı sadece doğrulanmış uygulamanın launch aşamasını başlatır; yönetici
   pencereyi otomatik kullanma veya eski grant'i geri açma izni değildir. Resume
   ancak ilgili yetki/identity kontrolleri ve yeni observation tamamlanınca olur.
8. Reject veya Stop terminal cancellation/rejection yoluna gider, grant önce
   revoke edilir. Pause bu yolu değiştirmez; geç onay/araç yanıtı görevi diriltmez.

## CLI, kota ve kalıcılık

Pause, “aynı model turunu sınırsız açık tut” demek değildir. Önce pause intent'i
ve run kimlikleri kaydedilir, yan etki kapıları kapanır. Gerekirse mevcut CLI'ler
kooperatif cancel/drain edilir; bunların cancelled sonucu task failure sayılmaz
(pause-owned run ID'leriyle ayrılır). Cleanup unconfirmed ise resume engellenir.
Kullanıcı gerçekten onaylayana kadar yeni model turu veya polling kaynaklı model
çağrısı yapılmaz. Güvenli yeni tur aynı job'a bağlı yeni run ID alır; eski
sağlayıcı oturum bilgisi izin yerine kullanılmaz. Mevcut güvenli yeniden başlatma
sınırları bu tasarımla sessizce gevşetilmez.

Mevcut job evidence dizinine atomik `task-state.json`: task/conversation kimliği,
pause nedeni, request generation ve izin verilmeyen kapsamın özet metadata'sı.
Bu bir izin kaydı değil, tarihsel devam bağlamıdır. Bearer, ekran, hassas log veya
kimlik bilgisi içermez. Restart sonrası kullanıcıya “kesilmiş/onay bekleyen görev”
sunulur; hiçbir broker grant, CLI, UAC veya input otomatik canlanmaz. UI tekrar
onayı ve güncel identity şarttır. WriterJournal/RunEvidenceStore yetki deposu gibi
kullanılmaz; aynı verinin ikinci canlı otoritesi oluşturulmaz.

## Kabul testleri (öneri, henüz çalıştırılmadı)

| ID | Test | Beklenen |
|---|---|---|
| AP-01 | Kartı aç, fake clock'u 10 dakika ve 2 saat ilerlet | Task paused; finished_at/Squad complete yok; model start ve yeni input sayısı0. |
| AP-02 | Kart beklerken eski onaylı pencereye Jarvis/MCP/queued click | Yan etki0; eski bearer/snapshot reddi. |
| AP-03 | Geçerli onay, aynı scope+identity | Yeni session, fresh observation; ancak bundan sonra input. |
| AP-04 | Expired/duplicate/wrong chat/task/generation onayı | Grant0; başka görevi durdurmaz veya yenilemez. |
| AP-05 | Pause ile input/Stop/approve yarışını barrier ile sırala | Pause sınırından sonra yeni side effect0; Stop sonrası resume0. |
| AP-06 | Beklerken CLI exit/cancel/timeout ve cleanup failure | Task yanlış completed/failed olmaz; unconfirmed cleanup resume'u bloklar. |
| AP-07 | Restart ve pause checkpoint'i | Yalnız bağlam görünür; otomatik process/input/grant0; yeni onay şart. |
| AP-08 | HWND reuse, PID/start/EXE değişimi, locked desktop | Resume BLOCKED, girdi0; eski identity kullanılmaz. |
| AP-09 | WinError740 kartı ve UAC yanıtı | Tek kullanımlı launch, UAC otomasyonu0; Quartz yükseltilmez. |
| AP-10 | Full auto-approved normal istek / farklı yeni kapsam | Mevcut full tercihi korunur; hassas kapsam pause sınırını aşamaz. |
| AP-11 | UI panel/komut paleti/dar pencere ve Durdur | Pause görünür, Stop erişilebilir; animation girdi geciktirmez. LIVE slotunda denenir. |
| AP-12 | Kartı tekrarlı aç / eski callback sonrası yeni görev | Tek pending generation, çift launch/run/transaction0, eski token yeni lease'i yenileyemez. |

Backend testleri clock/fake window ile önce, UI testleri sonra, gerçek GUI kabulü
ayrı tek operatör slotunda yapılır. Bu dosya hiçbir durumu veya kabul sonucunu
bugün değiştirmez.
