# Quartz — isteğe bağlı Notion Custom Agent bağlantısı

Kaynak baseline: `ee41b4005be2fc52c31dbe540886977aa95331cb`.
Branch: `codex/notion-agent-integration`. Tarih: 1 Kasım 2026.

## Sözleşme

Resmî `ntn api` üzerinden Notion Agent API public beta kullanılır. Desktop
uygulamasının IPC'si, Codex'in bağlı Notion tokenı veya Workers deployment yoktur.
CLI kurulumu ChatGPT/Codex/Antigravity tercihini değiştirmez. Notion'daki mevcut
Custom Agent seçilir; model ve bulut araçları o ajanın Notion ayarlarıdır.
Bir model adını yazarak Kimi erişimi satın alınmış veya doğrulanmış sayılmaz.

Yalnız açık `@notion` mesajı veya backend'de `agent="notion"` seçimi bu sağlayıcıya
gider. Yalnız gönderilen mesaj aktarılır: proje dizini, dosyalar, tüm sohbet geçmişi,
masaüstü araçları ve yerel Tam Yetki talimatı otomatik aktarılmaz. Notion ajanının
bulut araçları kendi mevcut yetkileriyle çalışabilir; Quartz bunu yerel salt-okunur
izolasyon gibi sunmaz. Birlikte modu ve Squad'ın iki ajanlı akışı değiştirilmez.

## Kurulum ve gerçek bağlantı testi

Kaynak checkout'unda:

```powershell
python -B scripts/notion_agent.py install
python -B scripts/notion_agent.py login
python -B scripts/notion_agent.py agents --workspace <workspace-uuid>
python -B scripts/notion_agent.py select --workspace <workspace-uuid> --agent <agent-uuid>
"Yalnız QUARTZ_NOTION_OK yaz." | python -B scripts/notion_agent.py send
```

`login`, resmî `ntn login --no-browser` komutunu kullanıcı terminalinde açar.
CLI'nin gösterdiği resmî URL, doğrulama kodu ve poll adımı izlenir; hesap girişi
otomatik yapılmaz. Anahtar sohbete, `.env` dosyasına veya Quartz belleğine yazılmaz.
Erişilebilir Custom Agent yoksa Notion'da önce oluşturulup yayımlanması ve uygun
erişim verilmesi gerekir. Bu adaptör ajan oluşturmaz, paylaşım değiştirmez.

Kurulum `%LOCALAPPDATA%/Quartz/bin/notion/0.23.25` altında sürümlüdür. Resmî npm
`ntn` arşivinin sabit SHA512 değeri doğrulanır, yalnız native Windows x64 binary
çıkarılır. npm lifecycle script'i, Node kurulumu veya genel PATH değişikliği yoktur.
Diğer mimariler desteklenmiş gibi gösterilmez. Güncelleme için sürüm/checksum
kaynak değişikliği ve inceleme gerekir; sessiz otomatik güncelleme yapılmaz.

## Oturum yaşam döngüsü

- API sürümü `2026-03-11`; query agents, create/update session, retrieve session,
  query events ve cancel session uçları kullanılır.
- Mesaj stdin JSON'dur; shell ve komut satırında prompt yoktur.
- API/oturum hataları Türkçe ve filtrelenmiş döner; stderr/başlıklar yayınlanmaz.
- Ortamdan token, alternatif Notion host ve düz metin keyring geçersiz kılınır;
  resmî OS keychain girişi kullanılır. CLI giriş gereksinimini aşan fallback yoktur.
- Bağlantı dosyası yalnız çalışma alanı/ajan ID ve adı tutar. Oturum sahipliği
  kayıtları mesaj/token tutmaz. Varsayılan yer `%LOCALAPPDATA%/Quartz/notion`.
- Önceden Quartz'ın oluşturmadığı veya başka ajan/çalışma alanına ait oturumlar
  sürdürülemez/iptal edilemez. Yerel ayar değişimi eski sohbeti yeni ajana bağlamaz.
- Devam yanıtı sequence baseline'ıyla eski yanıttan ayrılır; event ID tekilleştirilir.
- Gönderim zaman aşımında otomatik tekrar veya sağlayıcı/model değişimi yoktur.
  Sunucuda işlemin başlamış olabileceği açıkça belirtilir.
- `requires_action` otomatik onaylanmaz. Yerel tur BLOCKED olur; Notion'da
  incelenebilir. Runtime stop/shutdown kendi bu oturumunu iptal edebilir.
- İptal cevabı/kimliği doğrulanmadan uzaktaki görevin durduğu iddia edilmez.
- Yerel bekleme sınırı ve sayfalama sınırı vardır. Sınır aşımı başarı sayılmaz.

## Test ve kabul sınırı

`tests/test_notion_cli.py`, transport/kurulum doğrulamalarını;
`tests/test_notion_runtime.py`, oturum, iptal, continuation, kimlik ve sohbet
backend yönlendirmesini kapsar. Bunlar sahte transport ile çalışır; canlı model
yanıtı veya paketlenmiş GUI kabulü değildir.

Resmî CLI `0.23.25` bu bilgisayarda kuruldu, `--version`, `api --help`,
`login --help` ve `api v1/sessions --spec -X POST` çalıştı. Son işlem güncel
endpoint şemasını okudu; oturum/mesaj oluşturmadı. CLI ile ajan listesi okuma
denemesi bağlantı hatası döndürdü. Gerçek hesap girişi ve ajan yanıtı henüz
doğrulanmadı. Bağlı Codex Notion MCP erişimi, bu CLI'nin girişi yerine geçmez.

Son kaynak doğrulaması: 22 yeni test; tam güvenli koşu 683 test, 12 skip,
başarısızlık 0. Python sözdizimi 212 dosyada başarılı; gömülü JavaScript kontrolü
exit 0. Yayın denetimi staged kaynaklar ve geçmiş üzerinde PASS, bulgu 0.
Bu sayılar bu checkout ve koşuya aittir; bağımsız açık PR'lar dahil değildir.

### İlk Windows giriş akışı düzeltmesi

Yayımlanmış ajan hazırlandıktan sonraki gerçek CLI denemesinde eksik giriş
`exit 4 / No auth token found` ile gözlendi. Bu durum artık bozuk JSON gibi
sunulmuyor. OS keychain kullanımı ortamda açıkça zorunlu tutuluyor; mevcut bir
CLI config'inin `keyring=false` seçimi düz metin saklamaya neden olamıyor.

İlk giriş iki gerçek dizin hatası verdi: `Could not determine cache directory`
ve `NOTION_HOME ... existing directory`. Store Python'ın LocalAppData dizinini
özel LocalCache yoluna yönlendirdiği, Python'da `is_dir=True` iken native
PowerShell'de nominal yolun bulunmadığı ölçüldü. CLI/config ve cache dizinleri
Quartz profilinde oluşturulup `resolve(strict=True)` ile gerçek fiziksel yolları
native sürece verildi. Sistem ortam değişkenleri değiştirilmedi.

Düzeltmeden sonra resmî `ntn login --no-browser` exit 0 döndü, resmî Notion
yetkilendirme URL'si ve karşılaştırma kodu üretti. Bu giriş-akışı başlangıcının
canlı kanıtıdır; tarayıcı onayı, token redemption veya ajan yanıtı kabulü değildir.
Geçici URL/kodlar ve oturum dosyaları bu belgeye veya Git'e eklenmez.

Bu aşamada hedefli 25 test geçti; tam güvenli koşu 686 test, 12 skip, hata 0.
Giriş onayı ve adaptör üzerinden gerçek ajan yanıtı henüz bekleniyor.

## Frontend integration request — Claude/Codex entegrasyon aşaması

Bu PR `gui.py`, `ui/`, mevcut EXE, kullanıcı ayarları veya sohbet dosyalarını
değiştirmez. Kaynak backend'deki `@notion` desteği paketli ana sohbetin uçtan uca
çalıştığı anlamına gelmez. Frontend sahibinin koordinasyonu ile aşağıdakiler gerekir:

1. Açık `@notion` mesajını yerel REA/desktop/koordinasyon intercept'lerinden önce
   normal sohbet IPC'sine geçir. Devam eden yerel görevi bu mesajla yönlendirme.
2. Ajan seçimi ve bağlantı durumunda isteğe bağlı Notion satırını göster; model
   seçimi yerine seçilmiş Custom Agent adı ve bağlantı durumunu göster.
3. Kurulum, resmî giriş ve erişilebilir ajan seçimini sohbet/ayarlar üzerinden bağla.
   Kullanıcıya token yapıştırma veya plaintext depolama alternatifi sunma.
4. Yerel durdurma ile doğrulanmış uzaktan durdurmayı ayır; BLOCKED/onay bekleme
   durumunu ve belirsiz gönderim hatasını görünür kıl.
5. Resmî girişten sonra gerçek paketli ana sohbette gönder → yanıt → devam →
   durdur testini yap; Codex/Antigravity model ve sohbet regresyonlarını koru.

Bu frontend entegrasyonu, canlı hesap/ajan testi ve yeni EXE bu PR'ın tamamlanmış
kabulü olarak sunulmaz. Kamuya açık kaynak incelemesi hesap girişinden bağımsızdır.

## Resmî kaynaklar

- https://developers.notion.com/cli/get-started/installation
- https://developers.notion.com/cli/get-started/authentication
- https://developers.notion.com/cli/guides/api-requests
- https://developers.notion.com/guides/notion-agent-apis/overview
- https://developers.notion.com/reference/notion-agent-apis/update-session
- https://developers.notion.com/reference/notion-agent-apis/query-session-events
- https://developers.notion.com/reference/notion-agent-apis/cancel-session
