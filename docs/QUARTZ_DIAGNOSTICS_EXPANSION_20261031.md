# Sohbetten teşhis, sınırlı onarım ve seçilen uygulama incelemesi

## Kullanım

- **Quartz'ı kontrol et**: Mevcut asenkron paket/REA teşhisini sohbet kartında başlatır.
- **Quartz'ı onar**: Bilinen sağlam, aynı sürümün manifestli paket klasörünü seçtirir. Değişecek kaynaklar sohbet içinde gösterilir. Onay verilmeden yazılmaz.
- **Başka bir uygulamayı incele**: Yerel dosya seçicisinde tek bir EXE seçilir. Uygulama çalıştırılmaz; dosya kimliği, SHA-256, sınırlı PE başlığı ve destekleniyorsa REA statik paket bulguları kaydedilir.

Alıntılanan komutlar, açıklama soruları ve “araç kullanma” mesajları iş başlatmaz. Serbest biçimde her cümlenin anlaşılması iddia edilmez; bu ifadeler doğrulanmış girişlerdir.

## Sınırlar ve güven

Onarımın ilk kapsamı `_internal/assets/workspace.css` ve `_internal/assets/branding/quartz-q.ico` dosyalarıdır. EXE, DLL, hesap, konuşma, ayar, kayıt ve manifest değiştirilmez. Bir çalışma zamanı veya model bağlantı hatası için otomatik düzeltme garantisi verilmez.

Referans manifesti yayıncı kimlik doğrulaması değildir. Kullanıcı sağlam olduğunu bildiği paketi seçer ve bu güven kararını sohbet kartında açıkça onaylar. Referans EXE'nin mevcut EXE ile SHA-256 eşitliği ve iki kaynak dosyasının referans manifestiyle eşitliği ayrıca aranır. Kaynak baytları plan anında sabitlenir. Plan beş dakika geçerlidir ve tek kullanımlıktır. Hedef plan sonrası değişirse yazma reddedilir.

Yazmadan önce özel `Quartz/repair-backups/<plan-id>` klasörüne orijinaller ve makbuz kaydedilir. Her dosya geçici dosya + `os.replace` ile değiştirilir, sonra hash kontrol edilir. İşlem sırasında hata olursa yalnız bu işlemin yazdığı ve hâlâ beklenen içeriğe sahip dosyalar geri alınır. Başka yazıcının değişikliklerinin üstüne gidilmez. Böyle bir çakışmada `recovery_required` döner ve yedek korunur. İşlem ortasında işletim sistemi çökmesi için otomatik yeniden başlatma kurtarma servisi yoktur; makbuz ve orijinaller elle kurtarma için kalır. Görsel onarım sonucu bir sonraki uygulama açılışında ayrıca kontrol edilmelidir.

Dış uygulama hedefi yalnız GUI dosya seçicisinden gelir. Eski `diagnostics_start` IPC sözleşmesi dış hedef/komut kabul etmez. Dış uygulama servisi GUI sürecindedir; kapanışta iptal edilir. Komşu dosya, günlük, kullanıcı hesabı taraması veya hedef EXE çalıştırma yapılmaz. Bağlantılı yollar ve korunan Warband/Aster proje yolları reddedilir. Hedef sınırı 512 MiB; süre sınırı 180 saniyedir. REA adaptörü halen doğrulanmış PyInstaller özet şemasını kabul eder. Diğer formatlarda PE başlığı okunabilse de REA kapsamı UNKNOWN/NOT_TESTED kalabilir; buna hatasız uygulama denmez.

## Kabul ayrımı

- SOURCE/STATIC: doğal komut yönlendirmesi, onarım ön koşulları, tek uygulama, yedek/hash, rollback, değişen dosya reddi ve seçim iptali testleri.
- BUILT: izole PyInstaller paketi, kaynak/paket ve simge kontrolleri.
- LIVE: gerçek paketlenmiş ana sohbetten gönderim, ilerleme, iptal, sonuç kartı; ayrı izole kopyada onarım ve dosya seçimi. Oturum/ekran erişimi engellenirse BLOCKED; test doubles veya UIA başlangıç kanıtı bu kabul yerine geçmez.

Önceki kabul edilmiş çalışma dizini ve kullanıcı verileri geliştirme paketinin yerine otomatik değiştirilmez. GitHub yayını bu görevin parçası değildir.

## 31 Ekim doğrulama sonucu

| Alan | Sonuç | Kanıt / sınır |
|---|---|---|
| SOURCE/STATIC | PASS | 619 güvenli test, gömülü JS sözdizimi kontrolü |
| BUILT | PASS | PyInstaller, 50 kaynak/paket/helper/Q simgesi kontrolü |
| Temiz dağıtım | PASS | 1918 dosya; kişisel veri denetiminde 0 bulgu |
| Gerçek IPC + REA | PASS | 1917 dosya hash eşleşmesi; 3761 üye hash'i; 0 bütünlük çelişkisi; yetkisiz/dış hedef reddi; tekrar başlatma aynı iş kimliği |
| Gerçek dosya onarımı | VERIFIED, servis düzeyinde | Kabul edilmiş eski temiz paketin geçici kopyasında bozuk CSS onarıldı, yedek hash doğrulandı, ikinci uygulama reddedildi, EXE değişmedi. Ana sohbet UI kabulü değildir. |
| Onarım hata geri alma | SOURCE/STATIC PASS | İkinci yazma hatasında ilk yazma geri alındı; plan sonrası değişiklik reddedildi |
| Dış uygulama | PARTIAL | Gerçek Windows Not Defteri EXE: 200704 bayt, x64 PE, 7 bölüm; dosya değişmedi. Native PE için REA özet şeması henüz desteklenmediği için UNKNOWN. |
| Paketli uygulama açılışı | VERIFIED, UIA | Yeni adayın ana sohbeti, teşhis düğmesi, Q ve seçiciler göründü |
| Paketli sohbetten gönderim / onarım onayı / dosya seçimi | BLOCKED / NOT TESTED | İki ekran yakalama zaman aşımı; tıklamada `coordinate input geometry is unavailable`. Kör girdi gönderilmedi. |
| Kullanıcı verileri | PASS, ölçülen aralıkta | Bu oturum sırasında alınan hash snapshot'ından son kontrole 9 dosyada diff0. ASTER üzerinde işlem yapılmadı. |

İlk dış uygulama denemesinde REA sürüm kontrolü tamamlanmadı. Ayrı sürüm kontrolünde 6.8.0 doğrulandı; ikinci denemede REA exit0 döndü fakat PE şema kapsamı doğrulanamadı. İlk başarısız kayıt silinmedi, kalıcı nedenin çözüldüğü iddia edilmedi.

Yeni aday EXE SHA-256: `2491ee0be0ad0a393527d163b3d5e317f65196a5126f998dbf20197ba3e66a1f`.

Kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-diagnostics-expansion-20261031`.

- `build.log`: 619 test ve 50 paket kontrolü.
- `real-ipc/acceptance.json`: gerçek TCP IPC + yeni aday REA incelemesi.
- `real-services/acceptance.json`, `real-services-retry/acceptance.json`: geçici onarım ve Not Defteri incelemesi.
- `gui-uia.txt`, `gui-acceptance.json`: gerçek paketli pencere ve girdi engeli.
- `preservation.json`: dokuz dosya hash karşılaştırması.
- `clean-candidate/Quartz`: kişisel verisiz aday; mevcut `dist/Quartz` yerine dağıtılmadı.

Test penceresi Alt+F4 ile normal kapatıldı; sonraki süreç sorgusunda Quartz kalmadı. Kaynaklar GitHub'a gönderilmedi. Üç alanın sınırlı ilk uygulaması hazırdır; paketli ana sohbetin uçtan uca kabulü tamamlanmış değildir. Bir sonraki kabul, kullanılabilir ekran oturumunda yukarıdaki üç sohbet komutuyla yapılmalıdır. Genel uygulama hata ayıklama ve tüm paket dosyalarını otomatik onarma bu sürümün kapsamı değildir.

## Klavye erişimi düzeltmesi

Tıklama geometrisi olmadan da normal kullanıcı erişimi için Ctrl+L sohbet alanına odaklanır; ardından Enter mesajı gönderir. Kısayol tek başına görev başlatmaz. Görünür modal varken, alan gizliyken veya devre dışıyken odak çalmaz. IME yazımı ve basılı tutulan Enter tekrarları gönderim üretmez. Sekiz hedefli test ve JS kontrolü geçti. Bu düzeltme Windows ekran yakalama aracının zaman aşımını giderdiği iddiasını taşımaz; paketli klavye kabulü ayrıca kaydedilecek.

## İnsan gönderimi sonrası bulunan güncelleme sorunu

`9cb7b28764b5741b25e0308326fe03c1dfb31126574f4dbd3f08060574329dc5` adayında kullanıcı Gönder'e bastı. Gerçek ana sohbette mesaj ve teşhis kartı oluştu; %22, 100/1917 dosya ve iki PASS kontrolü UIA ile gözlemlendi. Arka uç `5ee7ec4c07804309aa1d52cd16da9fc1` işini tamamladı: 1917 dosya, 0 eksik/fark, REA 3761 üye hash'i, 0 çelişki, PASS. Kart sonraki gözlemde hâlâ %22 idi. Ana sohbetten gerçek başlatma VERIFIED; sonucun karta ulaştığı FAILED. Kullanıcının tıklamasından sonra da otomatik tıklama geometrisi ve güvenilir alan odağı doğrulanamadı.

Kaynakta durum sorgusunun hata/istisna alması halinde sessizce güncellemeyi sonlandırdığı belirlendi. Tam canlı istisna yakalanamadığından bu yol tek kesin kök neden olarak sunulmadı. Düzeltme: üç kontrollü tekrar, artan bekleme, görünür bağlantı uyarısı, “Durumu yeniden oku” düğmesi; hata durumunda iş kimliği korunur. Yanlış iş kimliği taşıyan yanıt kabul edilmez. Güncel terminal yanıt geldikten sonra sorgu sonlandırılır. Hedefli sekiz test ve JS doğrulaması geçti; düzeltilmiş paketin canlı kart güncellemesi ayrı kabul gerektirir.

Kanıtlar `C:\Users\LENAVO\.codex\backups\quartz-diagnostics-poll-20261031` altında: `human-submitted-backend-PASS.json`, `finding.json`, `build.log`. UIA gönderim kanıtı önceki `quartz-keyboard-chat-20261031/after-send-uia.json` dosyasında. Eski başarısızlık kaydı korunmuştur.
