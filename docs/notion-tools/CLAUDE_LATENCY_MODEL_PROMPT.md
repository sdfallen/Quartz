# Claude görevi — Notion hız deneyimi ve model alanı (eşit iş bölümü)

> DURDURULDU: 2026-11-01 kullanıcı kararıyla bu görev askıda.
> Yeni geliştirme/dağıtım yapma. Güncel karar: SUSPENDED.md.

Kullanıcı Codex ve Claude arasında eşit sorumluluk paylaşımını istedi. Bu
belge Claude'u otomatik başlatmaz; kullanıcı dış Claude oturumuna iletir.

## Ortak baseline ve sorumluluk

Yerel kaynak: `C:\Users\LENAVO\.codex\worktrees\quartz-notion-latency`
Dal: `codex/notion-latency-models`. Kendi ayrı dal/worktree'ni bu dalın son
commit'inden oluştur. Ana kullanıcı checkout'u ve kurulu EXE'yi değiştirme.

Önce AGENTS.md, docs/notion-tools/WORKER_BRIDGE_STATUS.md ve
CLAUDE_MAIN_CHAT_INTEGRATION.md oku. Önceki Claude teslimi d6174f6 bu dalın
baseline'ıdır; tekrar uygulama. E9c3ae2 eski pilot, paketli GUI kabulü değildir.

**Codex %50:** core/notion_runtime.py, core/notion_worker_task.py,
core/agent_chat.py; gerçek gecikme ölçümü, geçmiş olay filtresi, kuyruk
tekrarlarının azaltılması, model yetenek sözleşmesi, backend testleri ve
teslimlerin son birleştirilmesi.

**Claude %50:** gui.py, ui/*, frontend testleri ve izole paketli UI kabul
hazırlığı. Bunların dışına yazma; backend ihtiyacını Codex'e integration
request olarak ver. Aynı dosyaya paralel yazma. Codex backend'e devam edebilir.

## Görev A — gerçek model alanı

Notion seçildiğinde Codex/Antigravity gibi model bölgesinde Notion'a ait bir
alan görünmeli. Fakat sahte dropdown veya uygulanmayan model tercihi yok.

Resmî sözleşme:
- https://developers.notion.com/reference/notion-agent-apis/retrieve-agent
  yayımlanan model metadata'sını verir: auto veya pinned/id (id null olabilir).
- https://developers.notion.com/reference/notion-agent-apis/update-session
  request schema'sı additionalProperties=false; model override alanı YOK.
- Model değiştirmek için özel endpoint, prompt hilesi, gizli sağlayıcı devri,
  API anahtarı veya abonelik değişimi kullanma.

Mevcut onboarding_status -> providers.notion.model nesnesini kullan:
mode: auto|pinned|unknown, id: string|null, label: string,
selection_supported:false, managed_by:notion, reason:string.

1. Gerçek model etiketini göster; unknown durumunda kesin model uydurma.
2. "Notion'da yönetiliyor" açıklaması ve kısa Türkçe yardım sun.
3. Kullanıcı Notion'da değiştirip yayımladıktan sonra mevcut force refresh
   yoluyla gerçek model bilgisi yenilensin. Polling'de yeni ağ çağrısı üretme.
4. Güvenilir yönetim bağlantısı mevcutsa açılabilir; URL biçimi tahmin etme.
5. Doğrudan Quartz içinden seçim desteklenmiyorsa bu kısıtı görünür tut.
   Bu teslimi "model seçimi tamamen entegre" olarak raporlama.
6. Kullanıcının seçimine müdahale etme, yayını otomatik değiştirme.

## Görev B — hızlı ve anlaşılır sohbet deneyimi

1. Notion yanıtı gelirken kısmi metin mevcut sohbet balonunda güncellensin;
   son mesajı bekleyen görünmez buffer veya gereksiz render debounce olmasın.
2. Çift balon, scroll sıçraması ve kullanıcı yazısının silinmesini engelle.
3. Görev aşamaları gerçek backend durumundan gelsin. İlerleme yüzdesi uydurma.
4. Yeni metadata.timings alanını isteğe bağlı ayrıntıda göster:
   request_count, request_ms, submit_response_ms, first_text_ms, total_ms.
   first_text_ms, Quartz'ın ilk metni gözlemleme süresidir; modelin gerçek
   token üretim gecikmesi değildir. request_ms ağ/CLI toplamıdır; yalnız
   sunucunun hesaplama süresi değildir. Eksik ölçümü sıfır gösterme.
5. Rutin durum yenilemesinde tüm konuşmayı yeniden kurup animasyon başlatma.
6. Reduced motion/low-spec, Q teması ve mevcut agent renkleri korunsun.
7. İzin ve Stop akışını, scope/HMAC/IPC korumalarını aynen koru.

## Test ve teslim

Frontend testleri: auto/pinned/null/unknown, yenileme, desteklenmeyen seçimin
backend'e gitmemesi; kısmi metin, aynı mesajın güncellenmesi, Stop ve izin
kartı, sohbet değiştirme, reduced motion. Polling UI thread'ini kilitlemesin.

Gerçek paketli GUI testi yapabiliyorsan izole profil ve mevcut güvenli akışı
kullan. Kullanıcının Quartz'ını kapatma veya EXE'sini değiştirme. Kullanıcı
verisi/kimlik bilgisi kopyalama. Erişim engelinde BLOCKED yaz; mock tarayıcı
ve CLI testini paketli GUI kabulü olarak sunma.

`docs/notion-tools/CLAUDE_LATENCY_MODEL_REPORT.md` teslimi: commit, dosyalar,
testler, render ölçümleri ve sınırları, SOURCE/BUILT/LIVE ayrımı, eksikler.
Codex ile aynı baseline üzerinde git bundle/commit teslim et. ASTER'e,
sistem ayarlarına veya diğer sağlayıcıların model tercihlerine dokunma.
