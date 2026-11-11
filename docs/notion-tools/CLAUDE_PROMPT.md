# Claude 5.5 Opus görevi

Quartz'ın Notion araç entegrasyonunda ana sohbetin durum/izin/sonuç deneyimini
hazırla. Koordinatör Codex. Önce PLAN.md, CLAUDE.md ve mevcut ui/ kaynaklarını oku.

Başlangıç SHA: 451571251a9425a1bf32e757dd92ac74d5c6913b.
Güncel entegre kaynak C:\Users\LENAVO\.codex\worktrees\quartz-modern-notion.
Ortak checkout'ta değişiklik yapma; bu SHA'dan kendi ayrı worktree/clone'unda
claude/notion-tools-ui dalını aç. Eski masaüstü baseline'ından başlama.

Yalnız şuralara yaz:
- ui/document.py
- ui/styles.py
- ui/theme.py
- ui/notion_tools.py (yeni, dar durum bileşeni)
- tests/test_notion_tools_ui.py (yeni)
- docs/notion-tools/CLAUDE_REPORT.md (yeni)

Notion ajanı artık gerçek metin/kod analizi yapabiliyor, fakat yerel araç bağlantısı
henüz yok. Hazır olmayan özelliği bağlı veya başarılı gösterme. Mevcut mürekkep
mavisi tema, Q logosu, Codex buz mavisi/Antigravity ametist/Notion gri kimliği,
modern düzen, kod blokları, sohbet geçmişi ve azaltılmış hareket davranışı korunsun.
Yeni genel tasarım veya ikinci görev ekranı yapma.

Body ve uygulama JavaScript'i hâlâ gui.py içindedir. Yeni durum bileşenini
ui/notion_tools.py içinde hazırlayıp ui/document.py ile belgeye ekleyebilirsin.
Mevcut polling/render çağrı noktasına gereken hook'u Codex'e integration request
olarak teslim et; gui.py'yi taşıma veya bu dosyaya yazma.

PLAN.md'deki yerel notion_tools alanını render et. Alan bulunmuyorsa bugünkü
sohbet çalışsın. Checking/ready/blocked ile observing/awaiting_approval/executing/
verifying/completed/failed/cancelled durumları sade Türkçe ve gerçek backend
verisinden gelsin. Sadece model 'başardım' dedi diye verified gösterme.

Kullanıcı görevini aynı ana sohbetten versin; ayrı bilgisayar kontrol modu zorunlu
olmasın. Gereken kapsam mevcut izin kartında görünsün. Mevcut Stop ve izin API
adlarını koru; yeni backend endpoint'i icat etme. gui.py ve core/ dosyalarına
yazma; gereken backend bağlamalarını Codex'e integration request olarak ver.

Notion'ın kendi yürüttüğü iş ile Codex/Antigravity'ye devredilen iş açık ayrılsın.
Aktif operatör görünür olsun. Squad mesajları yetki sayılmasın. Teknik ayrıntılar
açılabilir kalsın. Çift onay/çift gönderim ve stale task ekranının yeni göreve
sızmasını önle; iptal edilen görev tekrar çalışıyormuş görünmesin.

Testler: veri yokken uyumluluk, sadece sohbet, bağlanma hatası, izin bekleme/onay/
ret, Stop, duplicate güncelleme, geç gelen eski task olayı, XSS/escape, Codex ve
Antigravity regresyonu, reduced-motion/Eco. Stop animasyon beklemesin. Mock UI
testlerini gerçek paketli Windows kabulü diye sunma. Windows GUI engelliyse
BLOCKED ve açık yeniden üretim adımları ver.

Commit SHA, değişen dosyalar, gerçek test sonuçları, ekran kanıtının hangi
ortamdan geldiği ve integration request ile teslim et. Kaynak dışında kullanıcı
sohbeti/.env/token/dist dosyalarını commit etme. PR açılabilir; merge, kurulum,
bulut agent ayarı ve EXE dağıtımı yapma. ASTER'e dokunma.
