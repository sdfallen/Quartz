# Notion araçları — iki teslimin entegrasyon incelemesi

Tarih: 2026-11-01. Koordinatör: Codex.
İzole entegrasyon dalı: `codex/notion-tools-integration`.
Başlangıç: `d3f5f7e`; üretim EXE değiştirilmedi, public release veya main merge yok.

## Teslim kararı

| Teslim | Kaynak | Hüküm |
|---|---|---|
| Claude UI | `d1590ba` -> `3e04465` | Render katmanı alındı; backend/poll hook'ları Codex tarafından eklendi. Windows paketinde LIVE kabul yok. |
| Gemini taşıma | `c74f2bd` -> `278f17e` | Yerel adaptör alındı ve kusurları düzeltildi. Gerçek Notion araç girişi sağlanmış değildir. Yol C üretim bağlantısı olarak kabul edilmedi. |

## Yeniden üretilen ve düzeltilen kusurlar

1. max_history=1 altında ikinci istek ilk kaydı siliyordu; ilk ID üçüncü çağrıda
   yeniden çalıştı (gerçek router çağrı sayısı 2). Artık kayıtlar silinmez; limitte
   yeni istek reddedilir, önceki sonuç yeniden yürütülmez.
2. Aynı request_id ile arguments veya tool/scope/project değişikliği eski sonucu
   döndürüyordu. Artık tam request fingerprint'i farklı içeriği reddeder.
3. Router exception metni sonuçta aynen görünüyordu. Sentetik özel metinle
   sızma doğrulandı; şimdi hata redakte edilir, yan etki belirsizliği kaydedilir.
   Router'ın NotionTransportError istisnası da kayıt atlayıp tekrar yürütmeye yol
   açamaz. Çalışan isteklerin testi gerçek eşzamanlı iki thread ile yapıldı.
4. İşlem sırasında deadline aşılması completed dönüyordu. Şimdi timeout ve
   uncertain döner; verified olmaz.
5. Şema True/NaN/Infinity/ek alan ve doğrudan dataclass ile bypass edilebiliyordu.
   Sıkı JSON, alan ve sayı doğrulaması eklendi; mutable sonuçlar cache'i değiştiremez.
6. Sonuç normalizasyonu sırasında Stop olursa commit anında da fence uygulanır.
7. UI, completed/none'dan daha yüksek revision ile completed/verified'a geçemiyordu.
   Bu düzeltildi; terminal durumdan executing'e dönüş hâlâ reddedilir.
8. DOM'da bulunup CSS/üst elemanı yüzünden görünmeyen Stop düğmesi kullanılabilir
   sayılabiliyordu. Gerçek geometry kontrolü eklendi. Render katmanı yeni işlemi
   kendi durduruyormuş gibi metin göstermiyor.

## Uzak bağlantı: gerçek engel

Resmî belgeler 2026-11-01 tarihinde kontrol edildi:

- [Query session events](https://developers.notion.com/reference/notion-agent-apis/query-session-events):
  araç adı ve yaşam döngüsü görünür; araç giriş/çıkışları olaylarda verilmez.
- [Create or update a session](https://developers.notion.com/reference/notion-agent-apis/update-session):
  aynı session'a yeni message göndermek desteklenir. Bu, yerel tool RPC endpoint'i
  veya tool result submit protokolü değildir.
- [Custom Agent MCP bağlantıları](https://www.notion.com/help/mcp-connections-for-custom-agents):
  Custom MCP için public URL'de hosted server ve Business/Enterprise planı gerekir.

Sonuç: Gemini raporundaki Yol C, istemciye authenticated structured request'in
nereden geleceğini çözmüyor. Agent message veya kod bloğu parse edilerek yerel
komut yürütülmeyecek; requires_action da yerel masaüstü yetkisi değildir.
Probe sadece local-simulation-only gösterir, cloud maliyeti bilinmiyor der ve
--allow-active-task için BLOCKED döndürür. Önceki sıfır maliyet/aktif bağlantı
iddiaları geri çekildi.

Mevcut resmî CLI üzerinden gerçek bulut sohbeti completed oldu. API metadata v3,
model Auto ve yalnız Notion connection gösterdi; local_tools=false korundu.
Ajan metninde bahsedilen cloud çalışma alanı araçları yerel Windows/Quartz araçları
olarak kabul edilmedi. Bu koşuda yerel araç çalıştırılmadı veya görsel erişim
doğrulanmadı. Özel hesap/oturum kimlikleri Git'e yazılmadı.

## Kanıt düzeyleri ve testler

- SOURCE/STATIC: Python syntax 227 dosya OK; GUI JS kontrolü hem ana blok hem
  Claude renderer'ını içerir ve exit 0 verdi.
- Hedefli gate/transport/UI/wiring testleri: 59 test geçti.
- Tam suite: 795 test koştu; hata yok, yardımcı EXE eksikliği nedeniyle 12 skip.
- Mevcut süreçle standalone QuartzDesktopMCP derlendi; ardından o 12 gerçek
  yerel Squad koordinasyon testi ayrıca koşuldu ve 12/12 geçti. Sonuçlar iki
  koşuya aittir; ilk suite'deki skip'ler gizlenmiyor.
- Test öncesi/sonrası 9 mevcut kullanıcı/ayar dosyası SHA256 karşılaştırması: diff0.
- Yerel kanıtlar: Codex backups/quartz-modern-notion-20261101/integration-review
  altında safe-tests.log, helper-build.log, coordination-tests.log,
  cloud-capability-check.json, protected-before.json, protected-after.json.
- BUILT: yalnız standalone yardımcı EXE. Yeni Quartz ana paketi derlenmiş veya
  kullanıcı kurulumuna alınmış değildir.
- LIVE VERIFIED: Notion bulut sohbeti ve yerel Squad helper roundtrip'leri kendi
  kapsamlarında. Notion -> yerel dosya/masaüstü/REA/Squad -> sonuç zinciri NOT TESTED.

## Sıradaki zorunlu kapı

Kullanıcı çalışma alanının Business/Enterprise olduğunu bildirdi. Abonelik
değiştirilmedi. Resmî CLI workers list çağrısı başarılı oldu ve erişilebilir Worker
sayısı 0 döndü; bu deploy yetkisini veya admin enablement'i tek başına kanıtlamaz.
Yeni Notion şeması ve Worker yayını için ayrıca onay gereklidir. Uygun resmî
bağlantı doğrulandıktan sonra
hosted MCP veya Worker tabanlı aracının yerel outbound istemciyle nasıl bağlanacağı,
kimlik doğrulama, Stop, kısa ömürlü scope ve veri aktarımı somutlaştırılmalı.
Yeni sunucu/tünel/paylaşım/yayın gerekli izin olmadan açılmayacak; yerel broker'ın
mevcut localhost bearer'ı buluta taşınmayacak. Alternatif sağlayıcıya gizli görev
devri yapılıp Notion'ın kendi araç kullanımı gibi gösterilmeyecek.

Birleşmiş UI şu anda doğru biçimde `availability=unavailable`, boş capabilities
ve task=null alır. Önce bağlantı ve gerçek çağrı kanıtlanmalı, sonra ready açılmalı.
Kullanıcı verileri ve çalışan uygulama korunarak bu kapıda duruldu. Entegrasyon
tamamlandı/hatasız/üretime hazır ilan edilmiyor.
