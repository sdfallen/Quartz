# Onaya sunulan tünelsiz Worker köprüsü

2026-11-01. Durum: TASARIM; henüz yaratılmış şema, dağıtılmış Worker veya LIVE test yok.
Kullanıcı Business/Enterprise planı olduğunu belirtti; mevcut CLI Worker listesi
okunabildi, erişilebilir Worker yok. Admin creation/deploy izni ayrıca doğrulanmalı.

## Neden

Session event API araç argümanlarını vermez; agent.message parse edilip komut
yapılmayacak. Desteklenen worker.tool çağrısının, yalnız bu entegrasyona ayrılmış
özel bir operasyon kuyruğuna doğrulanabilir istek yazması öneriliyor. Quartz
Notion'a dışarı doğru bağlanarak isteği okur; inbound port/tünel/public Windows
broker adresi yoktur. Worker resmi SDK context.notion ile sayfa/veri kaynağına
erişebilir. Bu tasarım henüz gerçek araç çağrısıyla kanıtlanmamıştır.

Resmî kaynaklar:
- https://developers.notion.com/workers/guides/tools
- https://developers.notion.com/workers/guides/api-client
- https://developers.notion.com/workers/reference/sdk
- https://developers.notion.com/workers/reference/limits

## Oluşturulması önerilen kapsam

1. Mevcut Quartz proje alanı altında, geniş paylaşım olmadan `Quartz Tool Queue`
   veri kaynağı. Var olan hafıza/sayfaların şeması değişmez. Kesin parent ve erişim
   oluşturma öncesinde erişilebilir kaynaklardan doğrulanır.
2. `Quartz Local Tools` adlı Notion Worker. Başlangıçta yalnız test projesinde
   salt okunur araç isteği enqueue ve sonuç okuma yeteneği. Kabiliyetler mevcut
   Quartz Custom Agent'a bağlanır; diğer ajan/kişilere paylaşım genişletilmez.
3. Secrets Worker environment ve Windows OS keychain'de; Notion sayfasında,
   model mesajında, .env/Git'te veya logda HMAC anahtarı bulunmaz.
4. Otomatik cron/schedule yok. Yerel poll yalnız kullanıcı görevi ve TTL boyunca
   yapılır. Ücretsiz olduğu iddia edilmez; Workers/Agent mevcut Notion kullanım
   ücretlerine ve kotalarına tabidir. Abonelik veya kredi limiti değiştirilmez.

## Minimal veri şeması (öneri)

| Alan | Amaç |
|---|---|
| Name / Request ID | Sabit işlem korelasyonu |
| Task ID / Session ID / Project ID | Yerelde başlatılmış görevle eşleşme |
| State | requested / claimed / completed / blocked / failed / cancelled / expired |
| Expires At | Kısa süreli yetki/işlem süresi; yeni görev süresi vermez |
| Signed Request | Kanonik şema + araç adı/argüman + yerel scope referansı + HMAC |
| Signed Result | Sınırlı sonuç + gerçek verification + belirsizlik + HMAC |

Masaüstü görüntüsü ilk salt okunur prototipe dahil değildir. Sonraki yetkili
görevlerde yalnız izinli hedefin gerekli log/metin/görüntüsü aktarılabilir;
genel disk veya bütün ekran kendiliğinden yüklenmez. Operasyon kuyruğu kalıcı
kişisel hafıza değildir; örnek/test verisi tutulur. Otomatik silme veya retention
job'ı bu onaya dahil değildir, ayrıca tanımlanmadan çalıştırılmaz.

## Doğrulama ve güvenlik

- Gerçek Worker tool çağrısı istemciyi planlamadan sadece request oluşturur;
  istek yerel HMAC, sahiplik, expiry ve aktif task/scope kontrollerini geçmedikçe
  dosya/terminal/GUI eylemi yapılamaz. Model scope_ref bilerek yetki elde etmez.
- Kuyruğa kullanıcı/belge içeriği eklenmesi çalıştırma izni değildir. Worker
  imzası kaynak bütünlüğüdür; görevin kapsamını onaylama yetkisi yine yereldedir.
- İşlem ID'leri süreçler arası durable ledger ile tutulmalı; restart veya API
  timeout sonrası sonucu belirsiz write otomatik yeniden yürütülmemeli. Mevcut
  process-local receipt tek başına yeterli değildir.
- Stop yerel capability'yi önce iptal eder. Uzak kuyruğun iptal yazımı başarısız
  olsa da yeni yerel eylem açılmaz. Yapılmış yan etki geri alınmış gibi sunulmaz.
- Worker'ın kendi sonucu `queued` olur; bunu tamamlandı diye sunmaz. Yerel
  sonuç hazır olduğunda mevcut session'a kanıt gönderilir ve gerçek araç sonucu
  ile eşleştirilir. Worker sandbox belleği/KV özelliği varsayılmaz.
- Önce disposable salt okunur dosya -> gerçek tool request -> yerel okuma ->
  sonuç -> aynı Notion oturumunda yorum kanıtlanır. Ardından proje yazımı,
  gerçek screenshot yorumlama, Desktop Broker/REA ve Squad ayrı kapılardır.
- Binding ve secret rotation, concurrency, cancellation, expiry ve sınır
  testleri geçmeden yazma/terminal/GUI araçları açılmaz.

## Gerekli onay

Kullanıcının AGENTS.md kuralı yeni Notion şeması oluşturmadan ve ilk kez yeni
bir yapıyı çalışma alanına eklemeden sormayı gerektiriyor. Bu iki özel bileşenin
oluşturulması ve sınırlı Worker yayını için onay istenir. Onay gelmeden bu belge
uygulanmış entegrasyon, veri kaynağı veya yayın değildir. Worker bağlantısının
ajan ayarlarından eklenmesi/yayımlanması gerekiyorsa o UI adımı da doğrulanır.
