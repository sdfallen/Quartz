# Claude'a iletilecek görev

Quartz'ı sistem piramidine oturtuyoruz. Yeni arayüz/özellik tasarlama;
mevcut ana sohbetin sunum sınırını temizle. Eski Notion görevleri iptal;
teslimlerini yeniden birleştirme. Notion yalnız dış ortak hafıza. ASTER yok.

Başlangıç kaynağı C:\Users\LENAVO\.codex\worktrees\quartz-architecture,
dal codex/architecture-pyramid-20261101. Ayrı clone/worktree kullan.
Önce docs/architecture/PYRAMID.md, TEAM.md, SOURCE_INVENTORY.json ve
docs/CLAUDE_FRONTEND_ARCHITECTURE.md oku. Son belge tarihsel, ilk ikisi güncel.
Kaynağa erişimin yoksa kod değişmiş gibi teslim verme; gereken bundle'ı belirt.

Sana ait: gui.py, ui/*, assets/workspace.css, frontend testleri ve raporun.
Backend, runtime, broker, güvenlik ve paket/CI dosyalarına yazma.

1. Önce GUI'deki servis oluşturma/iş kuralları ile salt sunum/native picker
   sorumluluklarını haritala. Her durumun asıl kaynağını yaz.
2. İlk küçük dilimde HTML body veya JS'in davranışı değişmeden ayrılabileceği
   sınırı seç. Yeni genel UI framework'ü kurma, dosyayı bir başka dev dosyaya
   taşımakla yetinme. Mevcut gui._HTML ve pywebview API uyumunu koru.
3. JS kontrol betiği ham gui.py'yi okuyor; JS taşınırsa kontrolün boş girdiyi
   başarı saymaması için Codex'e somut integration request ver. Codex ilgili
   kontrol/paket entegrasyonunu yapana kadar dilimini ship-ready ilan etme.
4. Native picker/onayın güvenilir GUI sınırını koru. Backend'e keyfî dosya
   yolu göndererek izin üretme. Tam Yetki, UAC veya Stop'a yeni anlam verme.
5. Mesaj akışı, partial response, conversation switch, model tercihleri,
   izin kartı ve Stop, reduced motion ve Q teması değişmemeli. Notion düğmesi
   geri gelmemeli; geçmiş mesajları silme.
6. Önce dar diff ve kontrat testleri, sonra erişebiliyorsan izole paketli GUI
   kontrolü. Mock tarayıcı/Node sonuçlarını LIVE olarak gösterme.

Teslim: docs/CLAUDE_PYRAMID_FRONTEND.md; baseline/commit, sınır tablosu,
değişiklik, testler, engeller, integration request ve geri alma yolu.
Ortak dosyalara ihtiyaçta beklemeden bağımsız alana devam et; aynı dosyaya
paralel yazma. Kullanıcı EXE'sini değiştirme. Kodun beklenen sonucu vermediği
yeri gizleme. Tek küçük dilimi doğrulamadan ikinci geniş refactor'a geçme.
