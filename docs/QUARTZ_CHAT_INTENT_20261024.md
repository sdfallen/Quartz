# Sohbet / işlem ayrımı

Kök nedenler: Warband proje seçimi bütün mesajları NaturalDesktopTask'a
gönderiyordu; normal sohbet runtime'ları da dosya/komut araçlarını devralabiliyordu.
İzin seçicisinin Full olması ayrıca selamlaşmayı bile yazma görevi yapabiliyordu.

## Yeni davranış

- `Merhaba`, `Warband hakkında ne düşünüyorsun?`, `NCO nasıl çalışıyor?`,
  `Nasıl test edebiliriz?`: araçsız sohbet. Proje seçimi bunu işlem yapmaz.
- `Kaynakları incele`, `Modu test et`, `Dosyayı güncelle`: gerçek görev.
  Warband görevleri yine UM köprüsüne, masaüstü görevleri mevcut onay akışına gider.
- Aktif görevde `Devam et` / `Durdur`: mevcut görev yönetimi. Aktif görev yokken
  belirsiz devam mesajı kendi kendine yeni bir işlem başlatmaz.
- `Araç kullanma, sadece sohbet edelim`: aktif bilgisayar görevini durdurur;
  sonraki yanıt araçsızdır. Normal bir yan soru mevcut görevi durdurmaz veya ona
  yeni araç talimatı olarak aktarılmaz.
- Salt sohbet için Full/proje yazma seçimi kullanılmaz, yazma onayı istenmez.
  Sunucu da bu ayrımı bağımsız uygular; yalnız UI kontrolüne güvenilmez.

Araçsız yanıtlar temiz geçici çalışma alanında çalışır, eski araçlı provider
oturumları devralınmaz. Uygulamadaki geçmiş silinmez; yakın sohbet bağlamı metin
olarak verilir. Codex'te mevcut per-run tool_guard ile shell/MCP/web/desktop
özellikleri kapatılır. Gemini'de mevcut PreToolUse deny helper'ı kullanılır.
Yazma izni, proje checkpoint'i veya masaüstü yetkisi oluşturulmaz. Modeller,
hesap girişi ve kullanıcı ayarları değiştirilmez.

Basit Birlikte sohbetinde iki ajan bir paralel tur yanıtlar. Açık tartışma/
değerlendirme/karşılaştırma veya `+1 Tur` isteği karşılıklı görüşmeyi korur.
Host'un yerel mesaj kaydı/Squad koordinasyonu modelin araç çağrısı değildir.

## Doğrulama ve sınırlar

`tests/test_message_intent.py`: normal/task/continuation, protected proje,
Full seçimi, no-tools guard, aktif görev yönlendirmesi ve tek grup turu.
Mevcut yazma onayı ve permission-denial testleri de korunur.
Gerçek CLI kanıtı: `labs/text-chat-20261024-151620/acceptance.json`.
gpt-6-luna/low ve gemini-3.8-flash-low/low, birer Türkçe sohbet yanıtını gerçek
runtime'da üretti; tool event, komut ve dosya değişikliği sıfırdı. Bu model/
runtime testidir, paketli ana sohbetten yapılmış tam GUI kabulü değildir.

Yerel, muhafazakâr niyet kuralları ekstra model çağrısı eklemez. Her doğal dil
ifadesini kusursuz anlayacağı garanti edilmez; belirsiz ifadeler araçsız kalır.
İşlem istendiğinde açık nesne+eylem kullanın (`logları incele`, `testi çalıştır`).
CLI açılış/ağ/model gecikmesi tamamen ortadan kalkmaz; FPS veya sabit hız artışı
iddia edilmez. ASTER kaynakları, kayıtları ve oyun süreçleri bu testte değişmez.

## Teslim durumu

- Son bağımsız tam regresyon: **374 test PASS**, 24 Ekim 2026 15:29.
- Paket kaynak/yardımcı protokol/CSS/Q ikonu eşleşmeleri: PASS.
- Yeni EXE SHA256:
  `539f2dce80affcae6b062d0088916ad1cbdc6cd729b168b1ba51ff272991dca5`.
- Kurulu paket:
  `C:/Users/LENAVO/Desktop/Jarvis config/dist/Quartz/Quartz.exe`.
- Kaynak checkpoint:
  `C:/Users/LENAVO/.codex/backups/quartz-chat-intent-20261024/agent-1792844684-5f1fc71fed2448bf9a81f76278c21f9e.zip`.
- İlk normal kapatma girişiminde pencere aktivasyonu iki kez
  `failed to activate captured window` hatası verdi. Kullanıcı Quartz'ı kendisi
  kapattı; zorla kapatma veya korumayı aşma denenmedi.
- 24 Ekim 22:45: **DEPLOYED**. Yeniden çalıştırılan 374 test PASS;
  paket ve yardımcı protokol kontrolleri PASS. Eski dağıtım kurtarılabilir:
  `C:/Users/LENAVO/.codex/backups/quartz-before-desktop-bridge-20261024-224539`.
- Teslim belgesi:
  `C:/Users/LENAVO/.codex/backups/quartz-chat-intent-package-20261024/deployment-receipt.json`.
  Kopyalama anında korunan veri dosyalarının tamamı byte-identical. Açılıştan
  sonra sohbet, proje, memory, .env ve mobile_access dosyaları hâlâ eşleşiyor;
  yalnız çalışma/açılış logları beklendiği gibi değişti.
- Yeni EXE açıldı; UIA ile pencere, eski sohbet geçmişi, seçili ASTER projesi,
  Gemini 3.8 Flash High / GPT-6-Sol Medium seçimleri ve Normal sohbet durumu
  yüklendikten sonra gözlendi (22:47). Ana sohbetten
  gönderilmiş uçtan uca yeni mesaj kabulü henüz **NOT TESTED**; gerçek CLI
  yanıt testiyle veya UIA açılış gözlemiyle karıştırılmamalıdır.
