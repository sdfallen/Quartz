# Gemini 3.8 Flash / Antigravity görevi

Quartz'ın Notion ajanına gerçek araç erişimi kazandırma işinde bağlantı protokolü
ve taşıma adaptörü senden soruluyor. Koordinatör Codex. Önce aynı klasördeki
PLAN.md'yi, CLAUDE.md'yi ve mevcut Notion runtime/CLI kaynaklarını oku.

Başlangıç SHA: 451571251a9425a1bf32e757dd92ac74d5c6913b.
Güncel entegre kaynak C:\Users\LENAVO\.codex\worktrees\quartz-modern-notion.
Burayı salt okunur baseline kabul et; kendi ayrı worktree/clone'unda
antigravity/notion-tool-transport dalında çalış. Masaüstündeki ana checkout eski
baseline'dadır; oradan veya eski performans dalından başlama.

Yalnız şu dosyalara yaz:
- core/notion_tool_transport.py (yeni)
- tests/test_notion_tool_transport.py (yeni)
- scripts/probe_notion_tool_transport.py (yeni)
- docs/notion-tools/GEMINI_REPORT.md (yeni)

İlk işin resmî Notion belgeleri ve mevcut resmî CLI ile gerçek araç çağrısı ve
araç sonucu döngüsünün nasıl kurulabildiğini kanıtlamak. Bulut Custom Agent'ın
yereldeki stdio MCP'ye kendiliğinden eriştiğini varsayma. requires_action yalnız
bir onay durumu olabilir; kullanıcı onayını tool execution sanma. API endpoint,
event veya tool result şeması uydurma. Belgelerin URL/tarihlerini kaydet.

Önce Codex'e feasibility teslimi ver: desteklenen yol, gereken yetkiler,
hosting/ücret/dağıtım gereksinimi, görüntü aktarımı ve sonuç devamı. Belgelenmiş
doğrudan bağlantı yoksa açıkça BLOCKED yaz; Workers/MCP gibi desteklenen yolu
öner. Alternatif yol Codex ile kararlaştırılmadan üretim bağlantısı kurma.
Private endpoint, token kopyalama, gizli IPC veya bulutun localhost'a eriştiği
varsayımı yok. Yeni ücret, yayın, tünel, dinleyici veya paylaşım açma.

Doğrulanmış yol için bağımlılıkları enjekte edilebilen dar taşıma modülü hazırla.
Bu modül yerel komut yürütmez; onaylı structured request'i Codex'in yerel
yönlendiricisine verir, sonucu aynı oturum/isteğe bağlayarak geri taşır.
Düz metin veya kod bloğunu komut gibi parse etme. Scope/izin model tarafından
verilmiş sayılmaz. PLAN.md'deki ortak alanlar yerel sözleşmedir, Notion API
alanı olduklarını varsayma. Mevcut model ve hesap tercihlerine dokunma.

Malformed event, yanlış session, tekrar/replay, timeout, disconnect, cancellation,
ambiguous submit ve binary/image payload sınırlarını test et. Yan etkili bir
isteği körlemesine yeniden gönderme. Probe varsayılanı read-only olsun;
gerçek görev/yan etki için açık test seçimi istesin. Gizli verileri loglama.

Diğer üretim dosyaları salt okunur; runtime değişikliği gerekiyorsa integration
request ver. Gerçek Notion testi yapamıyorsan mock'u canlı başarı gösterme.
Hedefli testleri çalıştır, güvenli test paketini mümkünse çalıştır. Commit SHA,
kanıt, gerçek komut sonuçları, sınırlamalar ve entegrasyon örneğiyle teslim et.
PR açılabilir; merge/deploy yapma. ASTER ve kullanıcı verilerine dokunma.
