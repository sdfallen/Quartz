# Sohbet silme

- Sol sohbet listesinde her sohbetin yanındaki **×** düğmesi tek sohbeti siler.
- **Bu projenin sohbetlerini temizle**, üstte seçili projeye ait sohbetleri
  topluca siler. Diğer projelerin sohbetlerine ve proje dosyalarına dokunmaz.
- Her iki işlem de isim/adet göstererek onay ister. Onay penceresi açıkken
  projenin sohbet listesi değişirse toplu silme reddedilir; yenilenip yeniden
  onaylanmalıdır.
- Çalışan sohbet/masaüstü görevi varken silme reddedilir. Önce görevi durdurun.
- Aktif sohbet silinirse aynı projede kalan son sohbet açılır; yoksa aynı
  proje, ajan ve model tercihleriyle boş bir sohbet açılır.

Silme, Quartz'ın yerel sohbet listesinden kaldırmadır; Codex/Gemini sağlayıcı
geçmişlerini veya proje/Squad dosyalarını silmez. İşlemden önce seçilen sohbetler
sohbet JSON dosyasının yanındaki `quartz_deleted_chats` klasörüne yerel kurtarma
yedeği olarak yazılır. Bu nedenle güvenli veri imhası değildir. Yedek veya yeni
sohbet dosyası yazılamazsa asıl sohbetler korunur. Yedekler otomatik silinmez.

Testler yalnız geçici sohbet depolarını kullanır; gerçek kullanıcı sohbetleri
bu geliştirme sırasında silinmez. Başarılı bir kaynak testi, paketli uygulamada
görsel kullanıcı kabulünün yapıldığı anlamına gelmez.

## 23 Ekim 2026 doğrulaması

`tests/test_conversation_delete.py`: 11 hedefli test geçti. Geçici depolarda
tekli/toplu silme, yeniden yükleme, yedek içeriği, proje/model tercihlerinin
korunması, onay ve görev kilitleri, değişmiş liste ve başarısız yazma sınandı.
Gerçek arayüz JavaScript'i Node altında çalıştırılarak iptal, tekli/toplu silme,
meşgul ve hata dalları kontrol edildi. Gömülü JavaScript sözdizimi geçti.

Son EXE kaynak-kod, yardımcı araç şeması, CSS ve Q marka kontrollerinin tamamı
geçti. SHA256:
`5921a316cd5709c191fee0b145a44b0f2e34693b122818cbf7a93dd78eafe643`.
Paket ve dağıtım kanıtları:
`C:/Users/LENAVO/.codex/backups/quartz-chat-delete-package-20261023`.
İlk derlemede eski kalan kod önbelleği tespit edilip yenilendi; hatalı paket
kurulmadı. Geliştirme öncesi ve sonrası kaynak checkpoint'leri
`C:/Users/LENAVO/.codex/backups/quartz-chat-delete-20261023` içinde korunur.

Son dağıtımda 356 test geçti; yerel kullanıcı verileri kopyalama öncesi/sonrası
eşleşti. Önceki uygulama
`quartz-before-desktop-bridge-20261023-221139` yedeğinde korundu. Yeni EXE normal
açıldı. Gerçek pencerenin erişilebilirlik ağacında dokuz eski sohbet, her
birinin ayrı silme düğmesi ve proje temizleme düğmesi doğrulandı. Var olan
mesajlar/model seçimleri yüklendi. Gerçek kullanıcı sohbeti silinmedi; silme
işlemlerinin yürütme testleri geçici depolarda yapıldı.
