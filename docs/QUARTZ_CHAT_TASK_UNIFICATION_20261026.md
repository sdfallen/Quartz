# Ana sohbet ve görev akışının birleştirilmesi — 26 Ekim 2026

## Sonuç ve kapsam

Normal kullanımda tek görev giriş noktası ana sohbet kutusudur. Ayrı
`Bilgisayar görevi başlat` düğmesi, Alt+B girişi, ikinci görev metin alanı ve
eski hazırlama/onay formuna yönlendiren yardım düğmesi kaldırıldı. Görev durumu
ve generation-bound Durdur kontrolü kaldı. Gerekli uygulama/log/UM kapsam onayı
mevcut sohbet kartında sorulur; sıradan tıklamalar için yeni görev yazılması
gerekmez. Gelişmiş tanılama API'leri kaldırılmadı, normal sohbet bunları ayrı
bir görev moduna geçmek için kullanmaz.

## Kanıtlanan sorunlar ve düzeltme

Kurulu sohbetin son gerçek kullanıcı mesajı:
`Pekala hadi bi deneme yapalım. Codex Masaüstünü incelermisin?`

Bu mesajın iki ajan yanıtı `completed`, `natural_task` alanları boştu. Türkçe
soru ekinin bitişik yazılması yüzünden istek görev sayılmamıştı. Ayrıca masaüstü
niyeti ve genel görev niyeti farklı fiil listeleri kullanıyordu. Kibar sorular
ve bazı doğrudan UI komutları dosya/araçsız sohbet yoluna düşebiliyordu.

- `misin/mısınız` eklerinin bitişik/ayrı yazımları görev tanımada kabul edilir.
- Ekrana bakma, uygulamaya geçme, pencere açma, düğmeye basma, kaydırma ve ekran
  görüntüsü isteme aynı görev sınıflandırıcısını kullanır.
- Alıntı/kod örnekleri komut olarak yürütülmez; açık araç kullanmama talimatı
  korunur. Normal sohbet araçlı göreve dönüştürülmez.
- Masaüstü ve Warband görevleri doğrudan mevcut `NaturalDesktopTask` yoluna
  gider. Normal sohbetin eski `coordination_prepare` formuna düşmesi kaldırıldı.
- Kaynak/dosya işleri mevcut checkpoint ve dosya izinli CLI yolunda kalır.
- Aynı sohbetteki ek görev talimatı etkin göreve iletilir; Durdur erişimi bırakır.
  Başka sohbetin operatörüne sessizce talimat gönderilmez.
- Seçili dosya yetkisi masaüstü yetkisi sayılmaz. IPC, broker, pencere kimliği,
  tek operatör, taze gözlem ve açık kapsam onayı kontrolleri korunur.

## Testler

| Kanıt düzeyi | Sonuç |
| --- | --- |
| SOURCE / regresyon | 466 test; 464 başarılı, 2 mevcut beklenen hata |
| JavaScript | Parse exit 0; gerçek `sendAgentMessage` fonksiyonuyla VM testi: tek dispatch, ayrı form yok, araçlı görev ikinci kez araçsız sohbete gönderilmiyor |
| Niyet/routing | Gerçek hatalı kullanıcı cümlesi, bitişik/ayrı soru ekleri ve Türkçe/İngilizce UI komutları aynı sohbetten Natural akışına ulaşıyor |
| Koruma | Sohbet/alıntı/araç kullanmama, dosya iş akışı, devam eden görev talimatı ve Stop regresyonları geçti |
| Gerçek CLI/MCP/Squad | `Api.coordination_route` üzerinden izole sohbet deposuyla Codex `gpt-6-luna/low` ve Antigravity `gemini-3.8-flash-low/low` gerçek araç çağırdı ve Squad mesajı gönderdi; ikisi de completed |
| Native input | Yukarıdaki bağlantı testinde pencere yok, broker audit 0; masaüstü yetkisi verilmedi ve GUI kabulü sayılmadı |
| Paketli GUI görsel kabulü | Mevcut Windows oturumunda ekran yakalama iki kez `window capture timed out`; gerçek tıklama/görüntü kabulü henüz verilmedi |

Gerçek CLI kanıtı:
`labs/natural-gateway-20261026-185823/transport-result.json`.
Komut: `python -B scripts/natural_gateway_acceptance.py --chat-entry`.
Bu test gerçek modelleri ve gerçek MCP/Squad taşımasını kullanır; host IPC ve
sohbet deposu disposable fixture'a yönlendirilmiştir. Paketli uygulamanın ana
sohbetinde kullanıcı tarafından gönderilmiş canlı görev testi değildir.

## Koruma ve teslim bilgileri

Değişiklik öncesi kaynak checkpoint'i:
`C:\Users\LENAVO\.codex\backups\quartz-chat-unification-20261026\agent-1793029819-5a8d683c03554d5e814f469b0a98624a.zip`.

Paket/teslim kanıtları için ayrılmış klasör:
`C:\Users\LENAVO\.codex\backups\quartz-chat-package-20261026`.

Kullanıcı sohbetleri, kayıtlı model seçimleri, Q ikonu, Squad, proje verileri ve
eski dağıtım korunarak teslim edilir. ASTER/Warband kaynakları ve kayıtları bu
görevde açılmadı/değiştirilmedi. API anahtarı veya hesap yapılandırması değiştirilmedi.

Kısa kullanım: Ana sohbete `Codex, masaüstünü incelermisin?` veya
`Codex, açık test uygulamasını incele. Gemini, test loglarını kontrol et.` yazın.
Gerekli kapsam kartı aynı sohbette görünür. İzin verildiğinde mevcut görev sürer;
başlatma düğmesi, yeni görev formu veya özel mesaj formatı gerekmez.

## Paketli teslim — son durum

- EXE SHA256: `1cd5cc92a6826146ffd3628f73c021288f9e06a378faa539cb6a6e613c232b7e`.
- Son kurulum kontrolü: 466 test tekrar geçti (2 mevcut beklenen hata).
- Paket/kaynak kod imzaları, helper, CSS ve Q ikonları eşleşti.
- Eski dağıtım: `C:\Users\LENAVO\.codex\backups\quartz-before-desktop-bridge-20261026-190715`.
- Kurulum öncesi/sonrası 32 veri dosyası karşılaştırıldı; fark 0.
- Kullanıcı açık uygulamayı normal biçimde kapattı; zorla süreç sonlandırılmadı.
- Yeni EXE açıldı. Gerçek UIA ağacında eski görev düğmesi yok, ana sohbet var;
  orijinal sohbet ve model seçimleri yüklendi.
- Paketli ana sohbetten görev gönderme: **BLOCKED**. Giriş alanına tıklama
  `coordinate input geometry is unavailable` hatası verdi. Korunan proje yerine
  fixture seçme denemesinde de seçim değişmedi; görev gönderilmedi. Rastgele
  koordinat, private IPC, injection veya otomatik izin onayı kullanılmadı.
- Gerçek GUI gözlem → kapsam onayı → eylem → doğrulama kabulü bu oturumda
  tamamlanmadı. Gerçek CLI/MCP/Squad sonucu bu kabulün yerine konulmadı.

Yerel kanıtlar: paket klasöründeki `deployment-receipt.json`,
`package-verification.json`, `preservation-deep.json`, `regression-final.log` ve
`labs/chat-entry-20261026/deployed-uia.txt`.
