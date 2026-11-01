# Antigravity'ye iletilecek görev

Quartz sistem piramidi: sen provider/runtime ve süreç katmanının sahibisin.
Yeni optimizasyon veya framework listesi değil, mevcut sistemin güvenilir
yaşam döngüsünü istiyoruz. Notion ajanı ve ASTER kapsam dışı.

Kaynak C:\Users\LENAVO\.codex\worktrees\quartz-architecture,
dal codex/architecture-pyramid-20261101. Ayrı worktree/branch kullan.
Önce docs/architecture/PYRAMID.md, TEAM.md ve SOURCE_INVENTORY.json oku.

Yazma alanın: core/codex_runtime.py, antigravity_runtime.py,
gemini_runtime.py, process_tree.py, async_snapshot.py, low_spec_optimizer.py;
bunların testleri ve docs/ANTIGRAVITY_PYRAMID_RUNTIME.md. GUI, main.py,
quartz_entry.py, orchestrator, izin/broker, kurulum/login ayarları, paket/CI
dosyaları salt okunur; ihtiyaçta Codex'e integration request.

1. Her runtime için start/get/cancel/shutdown, terminal durumlar,
   process/thread sahipliği, CLI oturumu ve hata çıkışını tek tabloda eşle.
2. Sahip olunan child ağacını doğrulayan mevcut process_tree mekanizmasını
   kullan. Başka sürece PID/isim tahminiyle müdahale etme. İptal isteği ile
   gerçek exit doğrulamasını ayrı tut. Beklenmeyen süreç/IO hatasını saklama.
3. Aynı görevin run/session kimliği ile application task_id'yi karıştırma.
   Run kayıtlarını yeni küresel task motoruna dönüştürme; küçük ortak adaptör
   sözleşmesi gerekiyorsa Codex'le paylaş.
4. Gerçek/tekrarlanabilir lifecycle kusuru bulursan checkpoint sonrası küçük
   düzeltme yap. Kanıt yoksa spekülatif rewrite yapma. Kullanıcı izinleri,
   model tercihi, hesap/kota ve provider seçimini değiştirme.
5. Boşta/açılış/çalışma/Stop/kapanış için CPU/RAM ölçümünü bütün owned process
   ağacıyla yap; aynı fixture ve capture koşulunu belirt. Donanım oturumu
   ölçülemiyorsa UNKNOWN, model işi uydurma. Screenshot/UIA netliğini azaltma.
6. AsyncSnapshot ve probe caching UI polling'de yeni model/login başlatmasın.
   Polling'i yalnız daha sık yaparak hız iddia etme.
7. Testler: başarısız start, normal exit, timeout, Stop, ardışık iki run,
   provider yokluğu, child cleanup ve geç çıktı. Kullanıcı dosyalarına yazma.

Teslim: baseline ve commit, harita, gerçek bulgu/düzeltme, test/ölçüm,
SOURCE/BUILT/LIVE ayrımı, engeller, integration request ve geri alma yolu.
Kendi paketini kullanıcıya dağıtma. Codex entegrasyonu tek elden yapacak.
