# Salt okunur Worker kurulumu — 2026-11-01

Kullanıcı özel operasyon kuyruğu ve sınırlı Worker yayınına açıkça izin verdi.
Bu not kaynak/test ve canlı sonuçları ayırır; tam Notion araç entegrasyonu kabulü
veya paketli GUI başarısı değildir.

## Gerçek oluşturulan ve doğrulanan

- Özel `Quartz Tool Queue` oluşturuldu (MCP'de parent verilmeden private root).
  Şema MCP ve Quartz'ın resmî ntn transportuyla tekrar okundu; 8 alan doğrulandı.
  Mevcut sayfa şeması veya paylaşımı değiştirilmedi.
- `Quartz Local Tools` resmî CLI ile yeni Worker olarak deploy edildi.
  İki tool capability'si sunucudan tekrar listelendi: quartzReadTestFile ve
  quartzReadResult. Webhook, cron, managed database veya inbound broker portu yok.
- Aynı workspace'e ait Worker'ın kimliği/adı ayrı get çağrısıyla doğrulandı.
  Gerçek queue/Worker ID'leri non-secret yerel profile ve Notion proje notuna
  kaydedilir; kaynakta sabitlenmez, workers.json Git dışındadır.
- İmza anahtarı Windows Credential Manager'a kaydedildi ve native readback eşitliği
  kontrol edildi. Worker environment ayarı CLI exit0 verdi. Notion API auth token'ı
  çıkarılmadı/kopyalanmadı. Anahtar Git, sayfa, transcript veya .env'ye yazılmadı.
- PyWin32 CredentialBlob'un bytes yerine Unicode istemesi ilk canlı kayıt
  denemesinde TypeError verdi. Hex/UTF-16 dönüşümü düzeltildi; gerçek native
  readback ve bir regresyon testi geçti. Başarısız deneme gizlenmiyor.

## Kaynak ve test

- Worker SDK 0.9.5, TypeScript 5.9.3, @types/node 22.9.0 ve package-lock kilitli.
  Lokal npm install --ignore-scripts ile yapıldı. Notion server build derlemesi
  de geçti. Local/compiler çıktısı canlı tool execution anlamına gelmez.
- Python targeted: 38 test geçti. Tam güvenli suite: 808 test, OK, skip yok.
- Node: 5 test geçti; ikisi arasındaki gerçek Python/Node UTF-8 imza roundtrip'i
  dahil. Python syntax: 231 dosya OK. Mock cloud driver testleri LIVE değildir.
- Gerçek disposable dosya okuması, scope/path/signature retleri, durable SQLite
  receipt, crash sonrası claimed kaydın tekrar yürütülmemesi, publish timeout,
  Stop ve aynı oturum devamının kaynak testleri eklendi.
- Test öncesi/sonrası 9 mevcut kullanıcı/ayar dosyasında hash diff0.
- Kanıtlar yerel Codex backups/quartz-modern-notion-20261101/worker-bridge
  altında; ham deploy çıktısı ve test kayıtları public Git'e eklenmedi.

## Canlı zincirde kalan blok

Notion ajanı sunucu metadata'sında hâlâ v3 ve yalnız eski Notion connection
gösteriyor; yeni Worker bağlantısı yok. Kurulum sohbetinin yönetici düzenleme
oturumu kullanıcı tarafında da başarısız oldu ve Worker kimliğini istedi.
Worker'ın varlığı ve workspace eşleşmesi yeniden doğrulandı; doğrudan yönetim
URL'si ve kimliği kullanıcıya verilecek.

Notion native pencere öne alındı; UIA içerik ağacı yalnız boş belge/titlebar
verdi. Taze pencereyle tekrar edilen iki screenshot çağrısı da tam olarak
`window capture timed out: timed out waiting on channel` hatası verdi.
Kör tıklama veya özel Notion endpoint'i kullanılmadı. Worker'ı ajan ayarlarına
bağlama/yayımlama adımı bu nedenle kullanıcıya devredildi.

## Hazır test sürücüsü

`scripts/notion_worker_acceptance.py --prepare` yalnız bağlantı tamamlandıktan
sonra çalıştırılır: yeni owned session ve 15 dakikalık imzalı fixture grant'i
oluşturur. Dosyadaki rastgele kanıt modele önceden gönderilmez.

`--run` yalnız bir kez istek gönderir, task/session'a özel kuyruğu okuyup imzalı
isteği doğrular; sadece tek fixture.txt dosyasını yerel manifest/file identity/hash
ile okur. Sonuç durable receipt ve imzalı kuyruk kaydına yazılır. Notion'dan
quartzReadResult çağrısı ve gerçek dosya kanıtı istenir.

requires_action otomatik onaylanmaz. Belirsiz POST otomatik tekrarlanmaz.
`--stop` bu fixture'ı kalıcı yerel stop dosyasıyla iptal eder; cron/arkaplan
servisi başlatılmaz. Hiçbir grant veya aktif test zamanlayıcısı kullanıcı Worker'ı
bağlamayı beklerken başlatılmadı.

Son hüküm: Worker DEPLOYED, kaynak/derleme/test PASS. Gerçek Notion Worker tool
-> yerel okuma -> aynı Notion oturumunda sonuç LIVE ACCEPTANCE BEKLİYOR.
Normal Quartz sohbetinde yerel araçlar henüz açılmadı, canlı EXE değiştirilmedi.
Terminal, dosya yazma, gerçek masaüstü kontrolü, REA ve Squad bu sınırlı prototipin
canlı kabulü olarak gösterilemez; ayrı sonraki kapılardır.
