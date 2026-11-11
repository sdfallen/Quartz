# Notion araç entegrasyonu — paralel çalışma sözleşmesi

Tarih: 2026-11-01. Koordinatör: Codex. Kaynak baseline: `451571251a9425a1bf32e757dd92ac74d5c6913b`.
Checkpoint branch: `codex/checkpoint-notion-tools-plan-20261101`.
Bu plan implementasyon veya canlı kabul değildir.

## Amaç ve mevcut durum

Notion Custom Agent v3 gerçek aritmetik, kod incelemesi, bağlamlı devam ve eski
oturum devamını yanıtladı. Bu, araç çalıştırma veya yerel masaüstü kabulü değildir.
Mevcut `NotionRuntime` local_tools=false kullanıyor; ana GUI rotası Notion için
yerel görev başlatmıyor. Bu sınırlar kanıtlı bağlantı hazır olmadan kaldırılmayacak.

Hedef: ana sohbetten Notion'ın yetkili araç isteklerini Quartz'ın mevcut görev,
Desktop Broker, proje checkpoint, REA ve Squad mekanizmalarına bağlamak.
Yeni genel ajan framework'ü veya ikinci masaüstü kontrol motoru oluşturulmayacak.

## Çalışma alanları

Her ajan bu baseline'dan ayrı worktree/clone ve ayrı branch açar. Mevcut ana
checkout'ta branch değiştirmez. Önceki performans dalı otomatik birleştirilmez.
Model isimleri kullanıcının görevlendirmesidir; bu belge oturum başlatmaz veya
sağlayıcı model erişimini doğrulamaz.

| Sahip | Branch | Yazma alanı |
|---|---|---|
| Gemini 3.8 Flash / Antigravity | `antigravity/notion-tool-transport` | Yeni `core/notion_tool_transport.py`, `tests/test_notion_tool_transport.py`, `scripts/probe_notion_tool_transport.py`, `docs/notion-tools/GEMINI_REPORT.md` |
| Claude 5.5 Opus | `claude/notion-tools-ui` | `ui/document.py`, `ui/styles.py`, `ui/theme.py`, yeni `ui/notion_tools.py`, yeni `tests/test_notion_tools_ui.py`, `docs/notion-tools/CLAUDE_REPORT.md` |
| Codex | `codex/modern-ui-notion` ve gerekli izole entegrasyon dalı | Mevcut `core/notion_runtime.py`, `core/notion_cli.py`, `core/agent_chat.py`, `core/multi_agent_service.py`, `gui.py`; mevcut broker/REA/Squad'a dar adaptasyon, yerel araç yönlendirici, entegrasyon testleri ve paketleme |

Başka dosya gerekiyorsa integration request ver; sahibiyle anlaşılmadan yazma.
Bu görev için yukarıdaki tablo önceki genel dosya sahipliği tablosunu dar kapsamda
günceller. Gemini ve Claude üretim EXE'sini değiştirmez, paket dağıtmaz, PR birleştirmez.

## Kapılar ve ortak sözleşme

1. Gemini resmî Notion API/CLI/MCP/Workers yeteneklerini araştırır. Gerçek tool
   çağrısı/sonucu döngüsü ile yalnız `requires_action` onay durumunu ayırır.
   Belgelenmiş bağlantı yoksa engeli ve alternatifini bildirir; sahte protokol yazmaz.
2. Codex doğrulanmış taşıma biçimini kabul eder. Barındırılan Worker, yeni ücret,
   yayın, paylaşım, ağ dinleyicisi/tünel veya yeni hesap yetkisi gerekiyorsa bu
   değişiklikler inceleme ve gerekli kullanıcı onayı olmadan devreye alınmaz.
3. Yerel yürütme mevcut broker üzerinden yapılır. Ajanın düz metni veya JSON kod
   bloğu executable komut değildir. Hangi sağlayıcının gerçekten yürüttüğü görünürdür.
4. Claude aşağıdaki yerel UI sözleşmesine göre çalışabilir; bunu Notion API şeması
   gibi sunamaz. Gerçek backend bağlanana kadar mock UI sonucu LIVE VERIFIED değildir.
5. Codex PR'ları inceler, birleştirir; gerçek Windows paketinde kabulü yürütür.

Yerel backend -> UI önerilen alanı `notion_tools` (mevcut payload'a ek alan):

```json
{
  "schema_version": 1,
  "availability": "unavailable",
  "capabilities": [],
  "task": null,
  "message": "Araç bağlantısı henüz doğrulanmadı."
}
```

`availability`: unavailable / checking / ready / blocked.
`task` doluysa: task_id, session_id, state, operator, verification, message.
`state`: observing / awaiting_approval / executing / verifying / completed /
blocked / failed / cancelled. `verification`: none / observed / verified.
Yalnız mevcut izin kartları ve Stop yolu kullanılır; yeni yetki veya Stop API'si
icat edilmez. Alan yoksa mevcut sohbet davranışı korunur.

Mevcut kaynakta body ve uygulama JS'i hâlâ gui.py içindedir; ui/document.py belgeyi
birleştirir. Claude yeni durumu dar bir ui/notion_tools.py bileşeninde sağlayıp
belge birleştirmesine ekleyebilir. gui.py içindeki mevcut polling/render çağrı
noktası için Codex'e integration request verir; GUI dosyasının tamamını taşımaz.

Yerel araç isteği tasarımında bulunması gereken bağlam: schema_version, task_id,
session_id, request_id, tool_name, arguments, project_id, scope_ref, deadline.
Bunlar yerel tasarım alanlarıdır; uzak API'nin desteklediği varsayılmaz. Yetki ve
kapsam yerelde doğrulanır; modelin gönderdiği scope_ref tek başına yetki vermez.
`deadline` taşıma adaptöründe yerel monotonic saate çevrilir; bulut timestamp'i
doğrudan karşılaştırılmaz ve yerel görev süresini uzatamaz.

## Kabul ve koruma

- Gerçek Notion isteği -> yetkili yerel okuma -> gerçek sonuç -> Notion'ın o
  sonucu kullanarak yanıt vermesi. İkinci tur bağlamı korur.
- Disposable projede değişiklik öncesi checkpoint -> dosya düzeltme -> gerçek
  test -> diff. Yalnız önerilen kod uygulanmış değişiklik sayılmaz.
- Disposable Windows test uygulamasında taze gözlem -> scoped eylem -> yeniden
  gözlem. Notion'a görüntü iletimi ve görüntüyü kullanabilmesi ayrıca doğrulanır;
  yalnız UIA metni veya dosya yolu verilmesi görsel yorumlama kabulü değildir.
- Gerçek Squad mesajı/görev sonucu; fare-klavye tek operatörde, yazıcı tek sahibinde.
- Duplicate/replay, eski scope/snapshot, yanlış oturum, iptal/Stop, timeout,
  bağlantı kopması ve izin reddi test edilir. Belirsiz yan etkili istek yeniden
  yürütülmez; Stop sonrası yeni yerel işlem başlatılmaz. Uzak işlemin durduğu
  doğrulanamıyorsa ayrı bildirilir.
- Kaynak/contract, mocked test, BUILT ve gerçek LIVE sonuçları ayrı raporlanır.
  Sahte terminal çıktısı, yerel sabit cevap ve gizli sağlayıcı devri kabul değildir.
- Mevcut Codex/Antigravity, sohbet geçmişi, Q teması ve animasyon tercihleri korunur.
  Tam yetki Windows yönetici yetkisi değildir. IPC auth, scope, taze gözlem,
  tek operatör, checkpoint ve Stop atlanmaz.
- Kullanıcı verileri/tokenlar/.env/ekran kanıtı Git'e konmaz; ASTER'e dokunulmaz.

Her teslim: commit SHA, değişen dosyalar, komutlar/gerçek sonuçlar, LIVE kapsamı,
bilinen engeller, integration request ve gerekiyorsa geri alma yolu içerir.
Tam güvenlik/hatasızlık vaat edilmez; açık kritik kusur veya başarısız zorunlu
kabul varsa tamamlandı denmez.
