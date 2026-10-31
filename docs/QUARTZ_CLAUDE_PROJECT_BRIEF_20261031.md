# Quartz — Claude için kapsamlı proje tanıtımı ve teknik devir raporu

Tarih: **31 Ekim 2026**

Kaynak deposu: <https://github.com/sdfallen/Quartz>

İncelenen commit: `cba9972a37f305a88c3b0047d9af34a7ab40d0e8`

Platform: **Windows 10/11 x64**

Ana dil: Kullanıcı arayüzü ve kullanıcı mesajları ağırlıklı olarak **Türkçe**
Durum: **Aktif geliştirme önizlemesi; kararlı son kullanıcı sürümü değil**

> **Güncel ürün kararı:** ASTER / Warband geliştirmesi resmî olarak rafa
> kaldırılmıştır. Mevcut entegrasyon kodu tarihsel ve korunan bir legacy modül
> olarak kalabilir; Quartz'ın güncel yol haritasına, kabul hedeflerine veya yeni
> ajan görevlerine dahil edilmemelidir.

Bu belge, Claude'un Quartz'ı yalnız dosya adlarından değil; ürün hedefi,
mimari sınırlar, güvenlik modeli, gerçek kabul seviyesi ve geliştirme
öncelikleriyle birlikte anlaması için hazırlanmıştır. Tarihsel raporlar yararlı
kanıt taşır, ancak güncel kaynak kodunun yerine geçmez.

---

## 1. Tek cümlede Quartz

Quartz; Codex ve Antigravity/Gemini tabanlı CLI ajanlarını, proje bağlamını,
görev kapsamlı Windows masaüstü kontrolünü, yerel uygulama incelemesini, Squad
koordinasyonunu ve doğrulanabilir çalışma kanıtlarını tek bir yerel Windows
sohbet uygulamasında birleştiren çoklu ajan geliştirme asistanıdır.

Quartz'ın hedefi yalnızca bir sohbet arayüzü olmak değildir. Amaç, kullanıcının:

> “Codex uygulamayı açıp sorunu bulsun ve düzeltsin; Antigravity logları ve
> değişiklikleri bağımsız kontrol etsin.”

gibi doğal bir görev yazabilmesi ve sistemin bu görev için gereken ajanları,
araçları, izinleri, checkpoint'i, gözlemi ve doğrulamayı ortak bir yaşam
döngüsünde yönetmesidir.

---

## 2. Ürün vizyonu

### 2.1 Ana hedef

Quartz'ın uzun vadeli hedefi, Codex Desktop benzeri doğal araç kullanımını
yerel, sağlayıcıdan bağımsız ve çoklu ajan uyumlu bir Windows uygulamasında
sunmaktır:

- Normal sohbet ile görev komutu aynı ana sohbet alanından verilir.
- Kullanıcı ayrı bir “bilgisayar kontrol modu” açmak zorunda kalmaz.
- Mesaj önce sohbet/görev/devam niyeti açısından değerlendirilir.
- Görev araç gerektiriyorsa ajan gerekli kapsamı ister.
- Fare ve klavye tek operatörde kalırken ikinci ajan eş zamanlı inceleme yapar.
- Her eylemden sonra taze ekran/UIA durumu okunur.
- Modelin “tamamlandı” demesi tek başına başarı değildir; sonuç gözlem, dosya,
  test, log veya proje sözleşmesiyle doğrulanır.
- Kullanıcı Stop ile görevi durdurabilir; yeni kapsam ayrıca onay gerektirir.

### 2.2 Quartz ne değildir?

Quartz:

- Bir Windows güvenlik sandbox'ı değildir.
- “Tam Yetki” seçildiğinde Windows yönetici token'ı kazanmaz.
- UAC, kilit ekranı, uzak/kapalı oturum ve daha yüksek integrity seviyesindeki
  pencereleri gizlice aşmaz.
- Ekrandaki metni sistem talimatı saymaz.
- REA ile bir EXE'yi inceleyince uygulamanın bütün davranışını öğrenmiş olmaz.
- Modelin kendi ağırlıklarını eğitmez veya kendi kaynak kodunu kontrolsüzce
  yeniden yazmaz.
- Rafa kaldırılmış ASTER/Warband alanında yeni geliştirme başlatmaz veya mevcut
  korumaları gerekçesiz değiştirmez.

---

## 3. Güncel ölçek ve teknik durum

İncelenen kaynak ağacında:

| Ölçüm | Güncel değer |
|---|---:|
| Git tarafından takip edilen dosya | 304 |
| Python dosyası | 207 |
| `core/` Python modülü | 60 |
| Test dosyası | 75 |
| Yaklaşık Python satırı | 36.186 |
| Güvenli regresyon testi | **661/661 PASS** |
| CI | GitHub Actions, `windows-latest`, PASS |
| Python | 3.13 |
| Node | 22, yalnız geliştirme/CLI araçları için |
| GUI | pywebview 6.2.1 + Edge WebView2 |
| Windows otomasyonu | pywinauto, Win32, PyAutoGUI, MSS |
| Paketleme | PyInstaller 6.20.0 |

Son başarılı CI koşusu:
<https://github.com/sdfallen/Quartz/actions/runs/41217816090>

Önemli yorum: 661 testin geçmesi kaynak seviyesinde güçlü bir regresyon kalkanı
sağlar. Bu sayı; gerçek Codex/Google hesabı, gerçek masaüstü, UAC, uzaktaki
oturum veya Warband oynanışının otomatik olarak kabul edildiği anlamına gelmez.

---

## 4. Yüksek seviye mimari

```mermaid
flowchart TD
    U[Kullanıcı / Ana sohbet] --> GUI[gui.py / WebView arayüzü]
    GUI --> IPC[main.py / yerel IPC]
    GUI --> INTENT[message_intent + diagnostics intent]

    INTENT -->|normal sohbet| CHAT[AgentChatService]
    INTENT -->|masaüstü görevi| NAT[NaturalDesktopTask]
    INTENT -->|Warband profili| WB[WarbandWorkspace / Universal Modder]
    INTENT -->|öz teşhis| DIAG[SelfDiagnostics / PackageRepair]

    CHAT --> MAS[MultiAgentService]
    MAS --> CODEX[CodexRuntime]
    MAS --> AGY[AntigravityRuntime]
    MAS --> GEM[GeminiRuntime / isteğe bağlı yol]
    MAS <--> SQUAD[SquadAdapter]

    NAT --> MCP[Görev kapsamlı yerel MCP]
    MCP --> BROKER[DesktopBroker]
    BROKER --> NATIVE[UIA + Win32 + ekran gözlemi]
    NAT --> LEARN[ApplicationLearning + REA]
    NAT --> ELEV[Uygulama özel UAC handoff]

    MAS --> CHECK[Checkpoint + WriterJournal]
    MAS --> EVID[RunEvidenceStore + kaynak doğrulama]
    WB --> UM[Universal Modder]
```

### Temel tasarım ilkesi

Quartz'ta “ajan”, “yetki”, “gözlem”, “eylem” ve “kanıt” aynı şey değildir:

1. Ajan görevi yorumlar.
2. Host görev kapsamını belirler.
3. Broker yalnız izinli pencere/uygulama için yetki verir.
4. Taze gözlem hedefin gerçekten mevcut olduğunu kanıtlar.
5. Eylem tek kullanımlık gözlem bağlamında yürütülür.
6. Sonuç yeni gözlem veya proje kanıtıyla doğrulanır.

Bu ayrım korunmalıdır.

---

## 5. Ana uygulama ve arayüz

### `quartz_entry.py`, `main.py`, `gui.py`

- `quartz_entry.py` kaynak modundaki ana başlangıç noktasıdır.
- `main.py`, yerel backend/IPC yaşam döngüsünü yönetir.
- `gui.py`, pywebview içindeki gömülü HTML/CSS/JavaScript arayüzünü ve Python
  API köprüsünü içerir.
- Ana sohbet; normal konuşma, proje görevi, iki ajanlı görev, masaüstü görevi,
  öz teşhis ve Warband görevlerinin ortak giriş noktasıdır.
- Sohbet geçmişi, proje seçimi, model seçimi, görev durumu, kısa ilerleme
  mesajları, izin kartları ve Stop aynı arayüzde sunulur.
- “Bilgisayar görevi başlat” şeklinde ayrı bir zorunlu kullanıcı akışı kaldırılıp
  görev yönlendirmesi ana sohbetle birleştirilmiştir.

### Arayüz tercihleri

- Modern koyu tema ve Quartz Q marka kimliği vardır.
- Kullanıcıya görünen metinler mümkün olduğunca Türkçedir.
- Teknik günlükler ana sohbeti kirletmemeli; ayrıntılar açılabilir teşhis
  alanlarında tutulmalıdır.
- Uzun görevler kısa ilerleme bilgisi göstermeli, fakat modelin her iç adımı
  kullanıcıya dökülmemelidir.

---

## 6. Mesaj niyeti ve doğal görev yönlendirmesi

### `core/message_intent.py`

Mesajlar üç temel sınıfa ayrılır:

- `conversation`: sohbet/açıklama; araç kullanılmaz.
- `task`: incele, düzelt, aç, test et, kontrol et gibi gerçek iş isteği.
- `continuation`: “devam et”, “tamam”, “durdur” gibi mevcut görev komutları.

Türkçe emir, rica ve geniş zaman kalıpları ile temel İngilizce görev fiilleri
desteklenir. Kod blokları ve alıntılar, yanlış görev tetiklememesi için niyet
analizinden çıkarılır. “Bu komut ne işe yarıyor?” gibi açıklama soruları görev
olarak yürütülmemelidir.

### Bilinen sınır

Niyet sınıflandırma deterministik ve muhafazakâr bir dil kuralı katmanıdır;
tam bir doğal dil modeli değildir. Yeni fiiller ve karmaşık Türkçe cümleler için
yanlış negatif/pozitif ihtimali vardır. Belirsiz mesajda araç çalıştırmamak,
yanlışlıkla bilgisayarı kontrol etmekten daha güvenlidir.

---

## 7. Ajanlar ve sağlayıcı çalışma zamanları

### `core/agent_chat.py`

Ana sohbetin ajan yaşam döngüsünü yönetir:

- Yalnız Codex
- Yalnız Antigravity/Google ajanı
- “Birlikte” modu
- Sohbet geçmişi ve proje bağlamı
- Paralel ajan turları
- Görev durumu ve kullanıcı devam mesajları

### `core/multi_agent_service.py`

- Codex ve Antigravity çalışma zamanlarını başlatır.
- Tek yazıcı kuralını uygular.
- Yazma yetkili işten önce gerçek checkpoint ister.
- WriterJournal ile yarım kalmış yazıcıları ve yeniden başlatma sonrası belirsiz
  durumu fail-closed ele alır.
- Görev sonunda değişen dosyaları toplar ve Python kaynak doğrulaması yapar.
- Çalışma kanıtını ve Squad bağlantısını run kaydına ekler.

### Sağlayıcılar

- `core/codex_runtime.py`: Codex CLI süreçleri, model/effort ve oturum devamı.
- `core/antigravity_runtime.py`: `agy` tabanlı Antigravity çalışma zamanı,
  Quartz MCP kaydı ve güvenli hook hazırlığı.
- `core/gemini_runtime.py`: Resmî Gemini CLI için bağımsız/fallback yol.
- `core/provider_manager.py`: Sağlayıcı sağlık/kota/hata sınıflandırması;
  otomatik ve sessiz sağlayıcı değiştirme yapmaz.

Kullanıcının mevcut hesap/CLI oturumu korunur. Quartz ücretli API anahtarına
sessizce geçmemelidir. Kota, model erişimi ve sağlayıcı kesintisi dış sistem
durumudur; Quartz bunu açıkça raporlamalıdır.

---

## 8. Çoklu ajan koordinasyonu

### Squad modeli

`core/squad_adapter.py` üzerinden Codex ve Antigravity aynı görev için bulgu
paylaşabilir. Temel rol ayrımı:

- **Operatör:** Gerekli masaüstü girdisini veya kaynak değişikliğini yapan tek ajan.
- **Gözlemci/inceleyici:** Log, kaynak, diff ve kanıtları bağımsız kontrol eder.

Fare ve klavyenin iki ajan tarafından aynı anda kullanılmasına izin verilmez.
Roller göreve göre değişebilir; sabit “Codex her zaman operatör” zorunluluğu
yoktur. Yazma gerektiren normal proje işlerinde tek yazıcı ilkesi korunur.

Warband profilinde Squad genel proje veritabanı yerine görev izolasyonlu kanıt
veritabanı kullanabilir.

---

## 9. Doğal masaüstü görev motoru

### `core/natural_desktop.py`

Bu modül ana sohbetten gelen doğal masaüstü görevlerinin merkezidir:

1. Görev ve proje bağlamı alınır.
2. Operatör/gözlemci rolleri belirlenir.
3. Göreve özel token ve yerel MCP sunucusu açılır.
4. Ajanlar yalnız Quartz'ın sağladığı sınırlı araçları görür.
5. Pencere/log erişimi gerekirse sohbet içinde izin kartı oluşur.
6. Onaydan sonra DesktopBroker kapsamı bağlar.
7. Ajan taze ekran/UIA gözlemi alır, eylem yapar ve yeniden gözlemler.
8. Sonuç kanıtı toplanır; Stop veya süre sınırı yaşam döngüsünü bitirir.

Görev araçları arasında şunlar bulunur:

- Görev bağlamı ve bekleme
- Squad mesajı gönderme/alma
- Onaylı log okuma
- Pencere listesi ve geçişi
- Pencere odağı, gözlem ve eylem
- Görünür UIA metniyle sonuç doğrulama
- Onaylı uygulamayı açma
- Sistem/pencere/medya için sınırlı Jarvis köprüsü
- Warband profilinde Universal Modder araçları

### İzin sonrası devam

İzin kartı onaylandığında eski model turu bitmiş olsa bile aynı görev ve token
ile kontrollü devam turu açılabilir. Tekrarlanan onay, callback veya release aynı
işlemi ikinci kez uygulamamalıdır. Stop yeni girişleri keser; açılmış Windows UAC
ekranını otomatik olarak kapatmaz.

---

## 10. Masaüstü kontrol güvenliği

### `core/desktop_broker.py`, `desktop_native.py`, `desktop_control.py`

Ana güvenlik özellikleri:

- Yetki belirli HWND/PID/start time/EXE kimliğine bağlanır.
- Yeni pencere veya child process otomatik güven kazanmaz.
- Ekran ve UIA birlikte kullanılır; biri diğerinin yerine kör doğrulama değildir.
- Eylem taze ve tek kullanımlık snapshot'a bağlıdır.
- Eski koordinat veya eski UIA referansı yeniden kullanılamaz.
- Pencere odağı değişirse önce hedefi yeniden doğrulamaya çalışır; güvenli biçimde
  geri alınamıyorsa rastgele koordinat göndermek yerine durur.
- Kullanıcı devralması, kilit ekranı, oturum kopması ve süreç kimliği değişimi
  ayrı hata nedenleri olarak ele alınır.
- Şifre alanları erişilebilirlik dökümüne alınmaz.
- Stop ve görev kapsamı korunur.

### Gerçek sınırlar

- Bazı oyunlar ve GPU ile çizilen özel UI'lar erişilebilirlik öğesi sunmaz.
- Uzak masaüstü bağlantısı kesildiğinde veya ekran kilitliyken görüntü yakalama
  çalışmayabilir.
- UAC secure desktop normal Quartz tarafından otomatik kontrol edilmez.
- Yükseltilmiş uygulama açılmış olsa bile normal yetkideki Quartz ona giriş
  gönderemeyebilir (UIPI).
- Bir pencereyi görebilmek, içindeki her kontrolü güvenle kullanabilmek değildir.

---

## 11. UAC ve yönetici isteyen uygulamalar

### `core/elevation.py`, `core/desktop_launch.py`

WinError 740 şu şekilde ele alınır:

1. Hedef yerel, bağlantısız, izinli bir `.exe` olmalıdır.
2. Dosya yolu, kimliği, boyutu/zamanı ve SHA-256 değeri bağlanır.
3. Sohbet içinde yalnız bu EXE için kullanıcı onayı istenir.
4. Onaydan sonra Windows'un desteklediği argümansız `runas` yolu çağrılır.
5. Quartz veya ajan ortamının tamamı yöneticiye yükseltilmez.
6. UAC'nin açılması görev başarısı sayılmaz; yeni pencere/işlem ayrıca
   doğrulanmalıdır.
7. Kullanıcı UAC'yi reddederse bu normal ve raporlanabilir bir sonuçtur.

Registry, güvenlik ilkesi, sürücü veya EXE manifesti otomatik değiştirilmez.

---

## 12. REA ve uygulama öğrenmesi

### İlgili modüller

- `core/rea_adapter.py`
- `core/artifact_diagnostics.py`
- `core/application_knowledge.py`

Quartz, kullanıcının izin verdiği gerçek EXE üzerinde salt okunur ve sınırlı
statik inceleme yapabilir. REA 6.8.0 isteğe bağlıdır ve
`%LOCALAPPDATA%\Quartz\tools\rea` altında izole hazırlanır.

Kaydedilebilen bilgiler:

- EXE SHA-256 ve dosya kimliği
- Boyut ve zaman/fingerprint
- PE mimarisi, bölüm sayısı, subsystem ve güvenlik bayrakları
- Desteklenen PyInstaller/REA envanter özetleri
- Sınırlı, tiplenmiş operasyon telemetrisi
- Önceki doğrulanmış gözlem/işlem sayıları

Kaydedilmeyenler:

- Ekrandan alınan serbest metinler
- Modelin talimatları
- Parola, çerez, API anahtarı
- Uygulamanın tüm kaynak kodu
- Güvenilir UI gezinme reçetesi
- Otomatik yeni yetki

Bilgi EXE hash'i ve kanonik dosya yoluna bağlıdır. Dosya değişirse veya kayıt
30 günü aşarsa yeniden doğrulama gerekir. REA verisi talimat değil kanıttır.

### Önemli ürün gerçeği

Quartz şu anda uygulamalar hakkında **statik ve sınırlı operasyonel bilgi**
biriktirir. “Bir kez inceledi, artık her şeyi biliyor” veya “kendi kendini
yeniden eğitti” iddiası doğru değildir. Kalıcı, doğrulanmış UI prosedürü
öğrenmesi gelecekteki ayrı bir araştırma alanıdır.

---

## 13. Proje ve dosya yazma güvenliği

### `core/project_registry.py`

- Kullanıcı projeleri açıkça kayıt edilir.
- Proje seçimi sohbet ve görev bağlamını izole eder.
- ASTER alt klasörünü genel proje olarak ekleyip korumayı aşmak reddedilir.

### `core/workspace_checkpoint.py`

- Yazma öncesi Git checkpoint'i veya tamamlanmış snapshot gerekir.
- `.env`, credential, token, yerel sohbet ve benzeri özel dosyalar arşive
  alınmaz.
- Değişen dosyalar görev bitiminde ayrıca hesaplanır.

### `core/writer_journal.py`

- Aynı projede çakışan yazıcıları engeller.
- Başlatma ile run kimliğinin kesinleşmesi arasındaki belirsizliği kaydeder.
- Uygulama çöküp yeniden açılırsa çözülmemiş yazıcı claim'i otomatik olarak
  güvenli sayılmaz; recovery/inceleme gerekir.

### `core/path_identity.py`

Windows'un aynı klasörü uzun yol ve 8.3 kısa yol ile göstermesi nedeniyle tüm
kritik proje/dosya kimlikleri kanonik yola dönüştürülür. Bu, writer kilidi,
checkpoint kanıtı, uygulama bilgisi ve CI davranışının tutarlı kalmasını sağlar.

---

## 14. Öz teşhis ve kontrollü onarım

### `core/self_diagnostics.py`

“Quartz'ı kontrol et” komutu:

- Kendi paket kimliğini ve gerekli dosyaları inceler.
- Release manifest hash'leriyle sınırlı karşılaştırma yapar.
- Destekleniyorsa REA ile salt okunur paket özeti çıkarır.
- Asenkron çalışır; GUI/IPC thread'ini bloke etmemelidir.
- Aynı aktif işi ikinci kez başlatmak yerine mevcut iş kimliğini döndürür.

### `core/package_repair.py`

“Quartz'ı onar” akışı:

- Bilinen sağlam ve manifestli bir referans paket ister.
- Değişecek dosyaları önceden gösterir.
- Kullanıcı onayı olmadan yazmaz.
- İşleme özel yedek ve makbuz oluşturur.
- Geçici dosya + atomik replace kullanır.
- Yalnız kendi yazdığı ve beklenen durumda kalan dosyaları geri alır.
- Başka yazıcının değişikliğini ezmez; belirsiz durumda recovery_required verir.

Öz teşhis veya onarım ASTER/Warband'a dokunmaz.

---

## 15. Bağımsız kurulum ve onboarding

### Hedef

Quartz'ın çalışması için Codex Desktop veya Antigravity Desktop/IDE kurulması
zorunlu değildir. Resmî hafif CLI araçları yeterlidir.

### `core/cli_installer.py`

- Açık yol, yönetilen Quartz bin klasörü, manifest ve PATH üzerinden CLI keşfi.
- Gerekirse resmî Node LTS Windows ZIP'i SHA-256 doğrulamasıyla indirir.
- Codex/Gemini paketlerini sabit sürüm ve npm integrity ile hazırlar.
- Global npm kurulumu ve kalıcı PATH/registry değişikliği yapmaz.
- npm lifecycle scriptlerini `--ignore-scripts` ile kapatır.
- Paket `bin` girişini doğrular; paket dışına çıkan yol reddedilir.
- `--version` geçmeden kurulum manifestini yayımlamaz.

### `core/onboarding.py`, `core/windows_prerequisites.py`

- İlk açılışta Türkçe “Quartz'a Hoş Geldiniz” akışı.
- Yalnız Codex veya yalnız Google ajanıyla çalışmaya izin verir.
- Eksik sağlayıcı nazikçe pasif görünür.
- Hesap girişi resmî CLI/tarayıcı akışında kullanıcı tarafından tamamlanır.
- Quartz parola veya doğrulama kodu toplamaz.
- API anahtarı seçeneği isteğe bağlıdır ve ücret/kota ayrımı kullanıcıya
  açıkça belirtilmelidir.
- WebView2 eksikse resmî Evergreen bootstrapper yoluna yönlendirilir.
- `.env` ve bağlantı metadata'sı atomik/geri alınabilir biçimde yazılır.

### Güncel kabul sınırı

İzole temiz profil ve CLI kurulum fixture'ları doğrulanmıştır. Ancak farklı bir
fiziksel temiz Windows bilgisayarda gerçek hesap girişinden gerçek model görevine
kadar olan uçtan uca kabul hâlâ ayrıca yapılmalıdır.

---

## 16. Arşivlenmiş Warband / ASTER / Universal Modder entegrasyonu

**Durum: SHELVED / OUT OF CURRENT SCOPE.**

Quartz geçmişte Mount & Blade: Warband için geliştirilen `AI_Island_Test` /
ASTER moduyla çalışacak özel bir adaptör kazanmıştır. ASTER artık aktif kullanıcı
projesi veya Quartz geliştirme önceliği değildir. Proje kökü Quartz reposunda
değildir; tipik tarihsel yerel konum `C:\WarbandIsland`dır.

### Kesin kural

Bu legacy alan tekrar etkinleştirilmedikçe hiçbir ajan Warband görevi başlatmamalı,
oyunu açmamalı veya `C:\WarbandIsland` üzerinde işlem yapmamalıdır. Kullanıcı
ileride açıkça yeniden etkinleştirirse **Universal Modder ana orkestratör** olma
kuralı korunur; Quartz genel dosya veya genel masaüstü araçlarıyla projeyi
değiştiremez.

### `core/warband_workspace.py`

Üç temel görev yeteneği sunar:

- **Inspect:** kaynak, sözleşme, RGL, kimlik ve korunmuş varlık inceleme.
- **Develop:** UM checkpoint, exact hash/replacement, resmî Module System
  derlemesi ve preservation kontrolleri.
- **Play:** Standard150 geçici config lease, gerçek oyun gözlemi ve kontrollü
  oyuncu girdisi.

Korunan alanlar:

- Native/ASTER kimlikleri
- Dünya haritası, kaynaklar ve action sıraları
- Orijinal kayıtlar
- Universal Modder yedekleri
- Battle size lease ve geri yükleme
- SOURCE/STATIC, BUILT ve LIVE kanıt ayrımı

Bu bölüm yalnız tarihsel mimariyi ve mevcut güvenlik sınırlarını belgelendirir;
Gate B, Gate C–G veya yeni oyun içeriği güncel Quartz çalışma planında değildir.

---

## 17. Düşük donanım yaklaşımı

`core/low_spec_optimizer.py` ve ilgili frontend davranışları:

- Boşta gereksiz polling ve arka plan yükünü azaltmayı hedefler.
- Ekran/UIA netliğini tamamen yok etmeden tarama sıklığını sınırlar.
- Log temizliği yalnız kontrollü, yaş/boyut sınırlarıyla yapılmalıdır.
- Tüm süreç ağacı RAM/CPU ölçümü, yalnız ana süreç ölçümünden daha anlamlıdır.

Bu alan Antigravity ile paralel geliştirilmiştir. Performans sonucu sentetik
testten gerçek eski bilgisayar garantisi olarak çıkarılmamalıdır.

---

## 18. Yerel veriler ve gizlilik

Git'e kesinlikle eklenmemesi gereken başlıca veriler:

- `.env`, API anahtarları
- Codex/Google/Antigravity oturumları
- Sohbet geçmişi
- Quartz bellek ve proje kayıtları
- Ekran görüntüleri ve canlı loglar
- OAuth/token dosyaları
- Yerel `.squad` veritabanları
- Build/dist paketleri ve kullanıcıya özel EXE'ler

`.gitignore` ve `scripts/audit_publish.py` bu alanları korur. Public repo geçmişi
de denetlenir. Public kaynak deposu açık kaynak lisansı anlamına gelmez; güncel
`LICENSE` all-rights-reserved/source-visible durumundadır.

---

## 19. Test ve kanıt modeli

Quartz üç kanıt seviyesini ayırır:

### SOURCE / STATIC

Kodun, sözleşmenin veya statik doğrulamanın varlığı. Gerçek uygulama davranışı
kanıtı değildir.

### BUILT

PyInstaller/Module System/derleme adımının başarılı olması. Canlı kullanım
kanıtı değildir.

### LIVE / OBSERVED

Gerçek uygulama, pencere, oyun veya süreç üzerinde taze gözlemle doğrulanan
davranış. Kapsamı belirtilmelidir; tek başarılı fixture evrensel başarı değildir.

### Ana test komutları

```powershell
python -B scripts/audit_publish.py --history
python -B scripts/check_python_syntax.py
python -B scripts/check_gui_javascript.py
python -B scripts/run_safe_tests.py
```

GitHub Actions aynı denetimleri temiz Windows runner'ında çalıştırır. Testlerde
sağlayıcılar çoğunlukla mock edilir; ücret/kota tüketilmez.

### Önemli kabul araçları

- `scripts/natural_desktop_e2e_acceptance.py`
- `scripts/multiwindow_acceptance.py`
- `scripts/workflow_acceptance.py`
- `scripts/accept_cli_clean_install.py`
- `scripts/accept_self_diagnostics.py`
- `scripts/accept_diagnostics_expansion.py`
- `scripts/warband_adapter_acceptance.py`
- `scripts/verify_desktop_package.py`
- `scripts/verify_live_quartz_gui.py`

Bu betiklerin sonuçları koşul ve build ile birlikte değerlendirilmelidir.

---

## 20. Güncel güçlü yanlar

1. Ana sohbet ile görev girişinin birleşmiş olması.
2. Sohbet/görev ayrımı sayesinde her mesajda gereksiz araç çağrısının azalması.
3. Codex + Antigravity paralel rol mimarisi.
4. Tek operatör ve tek yazıcı kuralları.
5. Pencere/süreç kimliğine bağlı masaüstü izni.
6. Taze, tek kullanımlık gözlem ve sonuç doğrulaması.
7. Stop, timeout, callback ve idempotency savunmaları.
8. Yazma öncesi checkpoint ve yarım kalmış writer recovery.
9. Rafa kaldırılmış Warband kodunu genel yetkiden ayıran legacy koruma profili.
10. REA bulgularını izin veya talimat saymayan sınırlı öğrenme modeli.
11. Bağımsız CLI/onboarding ve kişisel verisiz dağıtım hazırlığı.
12. Geniş kaynak regresyon paketi ve public CI.
13. UAC'yi bypass etmek yerine uygulama özel handoff olarak ele alma.
14. Yayın öncesi gizli veri ve geçmiş Git nesnesi denetimi.

---

## 21. Bilinen eksikler ve riskler

### P0 — Güvenlik/yanlış başarı riski

- Masaüstü kontrolünde sonuç gözlemi yapılamadıysa başarı iddiası verilmemeli.
- Uzak/kapalı ekran, kilit ekranı, UIPI ve capture timeout ayrı nedenlerdir;
  otomatik olarak Quartz bug'ı veya başarı sayılmamalıdır.
- İzin kartı sonrası gerçek continuation akışı paketli ana sohbette farklı
  uygulamalarla daha geniş canlı kabul gerektirir.
- Writer recovery veya pending UAC durumunda sessiz yeniden deneme yapılmamalı.

### P1 — Ürün kabul açığı

- Temiz fiziksel Windows bilgisayarda kurulum → WebView2 → CLI → hesap girişi →
  gerçek model yanıtı → masaüstü görevi uçtan uca kabul edilmeli.
- Codex-only, Antigravity-only ve Birlikte modları gerçek paket üzerinde ayrı
  kabul edilmelidir.
- Farklı DPI/çoklu monitör/uzak masaüstü senaryoları genişletilmelidir.
- Paketli ana sohbet içinde izin, Stop, tekrar devam ve hata kurtarma testleri
  daha sistematik hâle getirilmelidir.

### P2 — Mimari borç

- `gui.py` büyük ve gömülü HTML/JS ile Python köprüsünü aynı dosyada taşır;
  dikkatli ve kademeli parçalama yararlı olabilir.
- Eski Jarvis araç yolu ile yeni NaturalDesktop/MCP yolu tamamen aynı sözleşme
  kalitesinde değildir.
- Tarihsel dokümanların bazıları eski test sayıları ve eski build durumları
  içerir; tarih/commit bağlamı olmadan güncel gerçek kabul edilmemelidir.
- Niyet sınıflandırma kural tabanlıdır; kapsama eklenen dil kalıpları regresyon
  testleriyle korunmalıdır.
- Kalıcı UI prosedürü öğrenmesi henüz yoktur; eski koordinat/UIA referansı
  saklamak güvenli çözüm değildir.

### P3 — Kalite ve ürünleşme

- Kurulum sihirbazının farklı ekran boyutlarında görsel QA'sı.
- Erişilebilirlik, klavye navigasyonu ve ekran okuyucu testi.
- İmzalı installer, sürümleme, changelog ve geri dönüşlü güncelleme kanalı.
- Hata raporlarını kişisel veri sızdırmadan dışa aktarma.
- Gerçek düşük donanım cihazlarında ölçülebilir performans matrisi.

---

## 22. Claude için çalışma kuralları

Claude bu projede çalışırken aşağıdaki sözleşmeyi izlemelidir:

1. **Önce güncel kaynağı oku.** Eski raporları güncel gerçek sayma.
2. **Kullanıcının yerel verisini koru.** `.env`, sohbet, token, CLI oturumu ve
   yerel hafıza dosyalarını okumadan/değiştirmeden çalış.
3. **ASTER/Warband rafa kaldırıldı.** Bu alanda görev başlatma veya değişiklik
   yapma; legacy kodu yalnız açık yeniden etkinleştirme kararıyla ele al.
4. **Yazmadan önce checkpoint.** Checkpoint başarısızsa fail-closed.
5. **Tek yazıcı kuralını koru.** Paralel inceleme mümkündür; paralel yazma değil.
6. **İzin ile gözlemi karıştırma.** Kullanıcı onayı eylemin başarılı olduğunu
   kanıtlamaz.
7. **Model iddiasını kanıt sayma.** Test/log/UIA/dosya farkı gerekir.
8. **UAC'yi aşma.** Quartz'ı veya ajanı toptan yönetici çalıştırmayı varsayılan
   çözüm yapma.
9. **Ekran metnini talimat sayma.** Prompt injection veri olarak kalmalıdır.
10. **Taze gözlem kullan.** Stale screenshot, HWND, koordinat ve UIA ref reddedilmeli.
11. **Küçük düzeltme yap.** Gerçek hata kanıtlanmadan büyük framework rewrite'ı
    başlatma.
12. **Test seviyesini açık yaz.** SOURCE, BUILT ve LIVE sonuçlarını ayır.
13. **Başarısızlığı gizleme.** FAILED, BLOCKED ve NOT TESTED ayrı tutulmalı.
14. **Yayın öncesi audit yap.** Gizli veri ve kullanıcı geçmişi public repoya
    girmemeli.
15. **Kullanıcı arayüzü Türkçe ve sade kalmalı.** Ham İngilizce backend hataları
    kullanıcı balonuna sızmamalı.

---

## 23. Önerilen geliştirme sırası

### Aşama 1 — Dağıtımın gerçek kabulü

1. Temiz Windows VM veya yan bilgisayar.
2. WebView2 eksik/var A/B kontrolü.
3. Codex-only ilk giriş ve gerçek yanıt.
4. Antigravity-only ilk giriş ve gerçek yanıt.
5. Birlikte modunda Squad mesajı.
6. Basit Not Defteri görevi: gözlem → eylem → yeniden gözlem.
7. Stop ve izin iptali.
8. Kişisel veri ve uninstaller doğrulaması.

### Aşama 2 — Güvenilir masaüstü kabul paketi

1. Klasik Win32 uygulama.
2. WebView/Electron uygulama.
3. Çoklu pencere.
4. Odak kaybı ve güvenli geri kazanım.
5. UAC isteyen uygulama, kullanıcı onayı ve UIPI sınırı.
6. Uzak ekran/lockscreen BLOCKED davranışı.
7. Aynı görevin ikinci kez başlatılması ve temiz state.

### Aşama 3 — Mimari sadeleştirme

1. `gui.py` içindeki frontend assetlerini kontrollü ayırma.
2. Legacy Jarvis araçları ile NaturalDesktop ortak sonuç sözleşmesi.
3. Tek görev yaşam döngüsü şeması.
4. Ortak kanıt ve hata kodu taksonomisi.
5. Tarihsel belgeleri aktif sözleşme ve arşiv olarak ayırma.

### Aşama 4 — Öğrenme ve kalite

1. Yalnız doğrulanmış, sürüm/hash bağlı UI semantiği.
2. Eski koordinat saklamadan güvenli yeniden keşif.
3. Kullanıcı tarafından görülebilir bilgi deposu yönetimi.
4. Gerçek cihaz performans matrisi.
5. İmzalı sürüm ve kontrollü güncelleme.

---

## 24. Geliştirici kurulumu

```powershell
git clone https://github.com/sdfallen/Quartz.git
cd Quartz
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B scripts/check_gui_javascript.py
.\.venv\Scripts\python.exe -B scripts/run_safe_tests.py
.\.venv\Scripts\python.exe quartz_entry.py
```

REA isteğe bağlı hazırlık:

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_rea_tool.py
```

Paketleme:

```powershell
.\.venv\Scripts\python.exe -B build.py --require-brand
```

Kişisel verisiz dağıtım:

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_distribution.py `
  "<staging>\dist\Quartz" "<boş-hedef>\Quartz"
```

Mevcut kurulu Quartz çalışırken paketi körlemesine değiştirmeyin. Güvenli
dağıtım; süreç kontrolü, kullanıcı verisi hash karşılaştırması, geri alınabilir
yedek ve dağıtım makbuzu gerektirir.

---

## 25. İlk okunması gereken dosyalar

Claude için önerilen okuma sırası:

1. `README.md`
2. `SECURITY.md`
3. `DESKTOP_OPERATOR.md`
4. `core/message_intent.py`
5. `core/agent_chat.py`
6. `core/multi_agent_service.py`
7. `core/natural_desktop.py`
8. `core/desktop_broker.py`
9. `core/desktop_native.py`
10. `core/workspace_checkpoint.py`
11. `core/writer_journal.py`
12. `core/application_knowledge.py`
13. `core/rea_adapter.py`
14. `core/onboarding.py`
15. `tests/` içindeki ilgili sözleşme testleri

Bir bug raporunda yalnız bu genel listeyi okumak yerine, hatanın çağrı zincirini
ve doğrudan ilişkili testleri takip etmek daha verimlidir.

---

## 26. Claude'a verilebilecek başlangıç prompt'u

Aşağıdaki metin bu raporla birlikte kullanılabilir:

> Quartz, Windows üzerinde çalışan yerel bir Codex + Antigravity çoklu ajan
> geliştirme asistanıdır. Ana sohbet, normal konuşma ve görevlerin tek giriş
> noktasıdır. Masaüstü kontrolü görev/pencere kapsamlı izin, tek operatör,
> taze tek kullanımlık gözlem ve sonuç doğrulamasıyla çalışır. Yazma öncesi
> checkpoint ve tek yazıcı zorunludur. REA statik kanıt üretir; talimat, izin
> veya tam davranış bilgisi sayılmaz. ASTER/Warband resmî olarak rafa
> kaldırılmıştır; bu alanda yeni görev başlatma. SOURCE, BUILT ve LIVE kanıt
> seviyelerini karıştırma.
> Önce güncel kaynak ve ilgili testleri incele; gerçek hata kanıtlanmadan büyük
> yeniden yazım yapma. Kullanıcı verisini, `.env` dosyasını, CLI oturumlarını,
> sohbet geçmişini ve korunan oyun kayıtlarını değiştirme. Değişiklik yaparsan
> hedefli testleri, tam güvenli regresyonu, yayın denetimini ve gerçek etki
> alanına uygun kabulü çalıştır. Başarısız veya test edilmemiş sonucu başarılı
> gösterme.

---

## 27. Nihai değerlendirme

Quartz sıradan bir “iki modele aynı prompt'u gönder” uygulamasından ileridedir.
Gerçek değeri; çoklu ajan rol ayrımı, masaüstü yetki hakemi, checkpoint/writer
recovery, uygulama özel UAC, sınırlı REA bilgisi, Universal Modder koruması ve
kanıt seviyelerini aynı ürün içinde birleştirmesidir.

Bugünkü en büyük eksik yeni özellik sayısı değil, farklı bilgisayar ve gerçek
hesap koşullarında uçtan uca ürün kabulidir. En doğru strateji; yeni büyük
framework eklemek yerine mevcut güçlü çekirdeği temiz makine, gerçek model,
gerçek masaüstü ve güvenli hata kurtarma senaryolarında sistematik biçimde
kanıtlamaktır.

Quartz şu anda:

- **Kaynak geliştirme açısından güçlü ve testli,**
- **Yerel geliştirici kullanımı için işlevsel,**
- **Genel dağıtım açısından umut verici fakat hâlâ önizleme,**
- **Rafa kaldırılmış Warband entegrasyonunu yalnız legacy koruma olarak tutan,**
- **Son kullanıcı ürünü hâline gelmek için canlı kabul ve sadeleştirme isteyen**
  bir platformdur.
