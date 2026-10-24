# Ana sohbetten doğal masaüstü görevi — 22 Ekim 2026

Durum: ANA SOHBET BAŞLANGICI CANLI GÖZLENDİ; UÇTAN UCA GÖRSEL KABUL BLOCKED. Kaynak testi canlı GUI kabulü değildir.

## Desteklenen entegrasyon kararı

Resmî [app-server](https://learn.chatgpt.com/docs/app-server), [SDK](https://learn.chatgpt.com/docs/codex-sdk), [CLI MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [kimlik doğrulama](https://learn.chatgpt.com/docs/auth) ve [Computer Use](https://learn.chatgpt.com/docs/computer-use) belgeleri incelendi.

- App-server, özel istemciler için belgelenmiş görev/olay/onay protokolüdür. Mevcut Quartz bunu kullanmıyor; CLI `exec --json` kullanıyor.
- SDK bir başka desteklenen uygulama entegrasyonudur; bu iş için çalışan CLI yaşam döngüsünü bütünüyle taşımak gerekmiyor.
- Desktop Computer Use'un Quartz'ın yeniden kullanabileceği belgelenmiş bir host servisi/IPC uç noktası bulunamadı. Desktop'ın özel servislerine bağlanılmadı.
- Seçilen yol: mevcut CLI girişleri + kamuya açık MCP + Quartz'ın kendi kapsamlı Desktop Broker'ı. `codex login status`: ChatGPT girişi. Yeni ücretli API anahtarı, hesap veya runtime gerekmiyor.

## Uygulanan akış

`gui.coordination_route` normal masaüstü görevini `NaturalDesktopTask` üzerinden başlatır. Bu yalnız modelin araç seçimini başlatır; pencere izni değildir.

1. Codex ve Antigravity seçilmiş modellerle ayrı CLI süreçlerinde çalışır. Görev metnindeki roller kullanılır; ikinci ajan sabit log özetleyici değildir.
2. `task_context`: yalnız pencere/proje-log metadata'sı ve gerçek Squad mesajları.
3. Operatör `desktop_request_access` ile ihtiyaç duyduğu gerçek HWND/PID/start/exe kimliklerini seçer. Günlük okuma ayrıca kapsamda gösterilir.
4. Ana sohbette kısa izin kartı; bir kez açık onay. Ajanlar `task_wait` içinde bekler ve aynı görevde devam eder. Kullanıcı tekrar görev göndermek zorunda değildir.
5. Broker screenshot + UIA döndürür. MCP cevabında görüntü gerçek image bloğudur. Her girdi tek kullanımlık, en fazla 15 saniyelik snapshot'a bağlıdır; ardından yeni gözlem alınır.
6. Squad üzerinden iki yönlü bulgu ve kullanıcı ek talimatları iletilir. İkinci ajan token'ı masaüstü gözlemi/girdisi veremez.
7. `desktop_verify`, taze görüntüdeki tam UIA sonuç metnini kontrol eder. Modelin “başardım” cevabı doğrulama değildir. Bu kontrol yalnız belirtilen görünür koşulu doğrular; bütün işin doğruluğunu genellemez.
8. Stop, iptal, odak kaybı, süre bitimi veya hata capability'leri bırakır. Bekleyen çağrı da uyanır. Sonuç ve izinli gözlemler `%LOCALAPPDATA%/Quartz/task-evidence/<task-id>` altında saklanır.

## Korunan sınırlar ve açık kapsam

- IPC token'ı hâlâ yalnız aynı Quartz sürecinde. Dış `chat_status` denemesi `Unauthorized local IPC request` döndürdü; bu koruma aşılmadı.
- ASTER/Warband girdi yolu kapalı; Universal Modder adaptörü gerektirir. Bu çalışmada ASTER veya kayıtlarına erişilmedi.
- Güvenlik/kimlik doğrulama ekranları ve Quartz'ın kendi izin ekranları operatör hedefi olamaz.
- Yeni akış şu anda açık uygulamaların UI düzeltmeleri ve onaylı proje günlüklerine odaklıdır. Kaynak dosyası düzenleme için mevcut ayrı proje yazma/checkpoint akışı gerekir; yeni masaüstü token'ı dosya yazma yetkisi değildir.
- Normal sohbet yönlendirmesi amaç belirleyen yerel kurallar kullanır; her belirsiz cümleyi kusursuz anlayan genel model router'ı olduğu iddia edilmiyor.
- Mevcut gelişmiş EXE açma aracı korunur. Doğal akışta kapalı uygulamaları seçip başlatma kapsamının ayrı kabulü henüz yoktur.
- Screenshot/GUI engellenirse UIA'nın varlığı görsel kabul sayılmaz.

## Kabul fixture'ı

`labs/natural-desktop-20261022/QuartzTestApp.exe`, `scripts/NaturalDesktopFixture.cs` kaynağından derlendi. Yalnız kendi klasöründeki `test.log` ve `callback.json` dosyalarına yazar. Ağ/oyun/kullanıcı belgesi kullanmaz.

Referans renk rastgele seçilir ve yalnız boyanmış panelde görünür; UIA ve başlangıç günlüğü doğru rengin adını vermez. Ekrandaki mevcut renk farklıdır. Ajanın görüntüye dayanarak doğru temayı seçmesi, sonra `Durum: Düzeltildi` ve gerçek callback'i doğrulaması gerekir. Yanlış seçim sonucu saklanır; test bunu otomatik başarıya çevirmez.

Gerçek paketli uygulamada ayrı test projesi seçilerek ana sohbete yalnız şu cümle gönderilecek:

> Codex, açık test uygulamasındaki sorunu incele ve düzelt. Gemini, test loglarını kontrol et.

Canlı kabul gereksinimleri: sohbetten istenen gerçek izin, modelin gerçek image yorumlaması, bir operatör, eş zamanlı ikinci CLI, Squad bulgusu, gerçek UI değişikliği, taze son gözlem, callback/log eşleşmesi, Stop/lease bırakma. Fixture veya kaynak testinin başarısı bu kabulün yerine geçmez.

## Başlangıç koruması

Önceki kaynak: `C:/Users/LENAVO/.codex/backups/quartz-natural-desktop-20261022/before-source/agent-1792616803-978623b28ef74247a51ddae3ba0f1d03.zip`.

Tam eski dağıtım: aynı backup kökündeki `before-distribution`.

Eski EXE SHA256: `21d1404c79bf441612c8a228211d62e1f95fbd1c7e6e86ff39fc87db5242dbb6`.

## İlk gerçek ortam bulguları

- Eski paket PID 10000: erişilebilirlik ağacı ana sohbeti, Q simgesini ve gerçek model seçimlerini gösterdi.
- Screenshot denemeleri: `FrameArrived timed out: timed out waiting on channel`, ardından yenilenmiş pencereyle `window capture timed out: timed out waiting on channel`.
- UIA tıklama: `coordinate input geometry is unavailable`.
- Normal Alt+F4 kapanışı başarılı: uygulama günlüğünde `IPC action=shutdown`; süreç ve pencere gerçekten kayboldu. Zorla sonlandırılmadı.
- Bunlar yeni sürümün canlı kabul kanıtı değildir. Paketli yeni sürüm sonucu aşağıya eklenecek.

## Paketli ana sohbet koşusu ve bulunan yaşam döngüsü hatası

İlk doğrulanmış paket SHA256 `074973c604e45bc079018eac838099caed25dac5669a42d3fb7d7ccf7cabffab` geri alınabilir dağıtımla kuruldu; `327` güvenli test PASS ve tüm paket-içi modül/Q simgesi kontrolleri PASS. Mevcut sohbetler ve model seçimleri erişilebilirlik ağacında korundu. Bu paket, aşağıdaki onay-bekleme düzeltmesinden **öncedir**; son kaynakla aynı sürüm olarak gösterilmemelidir.

Gerçek paketli Quartz ana sohbetine kullanıcı örneğindeki tek cümle normal sohbet girdisiyle gönderildi. Ayrı Ajan Merkezi açılmadı. Kanıt: `%LOCALAPPDATA%/Quartz/task-evidence/c8fb4659410b4e43ba54062068fa4ba9/result.json`.

- Gerçek Codex `gpt-6-luna` ve Antigravity `gemini-3.8-flash-low` CLI süreçleri aynı göreve başladı; Codex gerçek test uygulaması HWND için sohbet-içi izin kartı açtı.
- Kullanıcı onayı verilmedi. Broker audit boş, test uygulaması `callback.json` oluşturmadı; hiçbir UI değişikliği/başarı iddia edilmedi. Görev sonucu `NOT VERIFIED`.
- Seçili eski sohbetin projesi `Squad Pilot` kaldığından Gemini'nin test fixture günlüğü kapsam dışında kaldı. Fixture ayrı bir proje olarak kayıtlı olsa da bu koşu fixture projesinde değildi. Bu ikinci ajan log kabulü değildir.
- Ajanlar izin beklerken CLI turlarını bitirdi ve görev erken `completed` oldu. Bu gerçek kod kusuru için `NaturalDesktopTask` güncellendi: izin kartı beklemede iken görev canlı kalır; terminal CLI turu onaydan sonra aynı task token, model ve kısıtlı MCP ile yeni tur başlatır. Girdi/önceki gözlem tekrarlanmaz. İzin süresi dolarsa görev sonlanır. Yeni kaynak testi bunu doğrular; yeni paketli kullanıcı-onay akışı henüz canlı kabul görmedi.
- Haricî test operatörünün pencere yakalaması yeni Quartz ve fixture için `FrameArrived timed out` / `window capture timed out` verdi. Bu, Quartz'ın kendi izin-sonrası broker yakalamasının başarısız olduğunun kanıtı değildir; o yol kullanıcı onayı olmadığı için denenmedi. Erişilebilirlik metni görülse de gerçek screenshot ve tıklama kanıtı yoktur. Görsel teşhis → tıklama → yeni görüntü → düzeldi doğrulaması **BLOCKED** olarak kalır.

İkinci paketli koşu: `9c4fcf18aff51c2ca648671f5e6c590bdc4effbfe2785fc8fab7b4b7d1dd8cc4` ile yeni fixture projesine bağlı, eski sohbetleri koruyan ayrı test sohbeti açıldı. Normal ana sohbetten yine yalnız kabul cümlesi gönderildi. Codex test penceresi HWND'sini, Gemini aynı projenin `test.log` dosyasını talep etti; birleşik kartta tam kapsam görüldü. İki gerçek CLI turu onay beklerken bitse de görev ve kart açık kaldı: yaşam döngüsü düzeltmesi **paketli canlı koşuda doğrulandı**. Kullanıcı onayı gelmediğinden ana sohbetten `Durdur` gönderildi; görev `cancelled / NOT VERIFIED` kapandı, broker girdi izni açılmadı. Kanıt: `%LOCALAPPDATA%/Quartz/task-evidence/393015d931f74362a5d085ca3f6d4758/result.json` ve aynı test sohbetinin mesajları.

İkinci koşuda tekrarlanan aynı-kapsam log isteğinin izin kartını yenilediği görüldü. Kaynakta aynı bekleyen kapsam için eski kart ID'sini koruyan ek düzeltme yapıldı ve hedefli test PASS. Bu küçük değişiklik ikinci paketli koşudan **sonradır**; son paketli tekrar ve insan onayı henüz yoktur.

## Gerçek sağlayıcı bağlantı testi

`labs/natural-gateway-20261022-002953/transport-result.json`: PASS — yalnız CLI/MCP/Squad transport kapsamı.

- Codex `gpt-6-luna / low`, Antigravity `gemini-3.8-flash-low / low` (sohbetteki mevcut seçimler).
- İki gerçek çalışma aralığı yaklaşık 9.43 saniye örtüştü. İki taraftan da gerçek `task_message` → Squad mesajı ve tamamlanma alındı.
- Hiç masaüstü izni verilmedi, native backend bu testte boştu; broker audit'i boş. Görsel/GUI hedef sonucu doğru biçimde `NOT VERIFIED` kaldı.
- Antigravity bazı izin dışı araç adlarını denedi; hook reddetti. Sonra izinli MCP yoluyla tamamladı. İzin yükseltmesi yapılmadı.
- CLI'nin `--mode auto` için bu Windows host'unda terminal sandbox bulunmadığı uyarısı korundu. MCP/hook sınırı OS düzeyinde mutlak sandbox olarak sunulmuyor.
- Kaynak derlemesi sırasında dosya değişikliği nedeniyle ilk staged paket `core.natural_desktop` bytecode kontrolünden geçmedi; kurulmadı. Yeniden derleme/tekrar hash kontrolü zorunlu tutuldu.

## Son teslim ve açık kabul

Son paket: `C:/Users/LENAVO/Desktop/Jarvis config/dist/Quartz/Quartz.exe`, SHA256 `7a377b21042cacc49c2fa88da02c5c880a96588db5647b16da0358b715767c14`. `329` güvenli test PASS; paket modülleri, yardımcı MCP hash'i, CSS ve onaylı Q simgesi kontrolleri PASS. Kurulum fişi: `C:/Users/LENAVO/.codex/backups/quartz-workspace-package-20261022-085140/deployment-receipt.json`. Eski dağıtım geri alınabilir yedekte: `C:/Users/LENAVO/.codex/backups/quartz-before-desktop-bridge-20261022-085617`.

Son paket normal açıldı; erişilebilirlik ağacı `ÇEVRİMİÇİ`, önceki `Naber` sohbeti, `Squad Pilot` proje seçimi ve önceki Gemini/Codex model seçimlerini gösterdi. Yedi eski sohbetin tamamı ve eski mesaj dizileri korundu; ayrı bir test sohbeti eklendi. `.env` ve `mobile_access.json` ilk dağıtım yedeğiyle hash-eş. Test fixture'ı kapatıldı; `callback.json` hiç oluşmadı. Kullanıcı onayı verilmediği için son paketle gerçek görüntü yorumlama, tıklama, taze görüntü ve UI sonucu **NOT VERIFIED**. Haricî test operatörünün screenshot servisi ayrıca zaman aşımına uğradı. Quartz broker'ın izin-sonrası capture yolu henüz değerlendirilmedi.

Bu nedenle karar: ana sohbetten görev yönlendirme, eş zamanlı gerçek CLI/Squad başlama ve sohbet-içi kapsamlı izin isteme **LIVE VERIFIED** (önceki paketli koşularda); son paketin açılış ve veri koruması **VERIFIED**. İzin sonrası uçtan uca masaüstü düzeltme **BLOCKED — açık kullanıcı onayı ve gerçek ekran görüntüsü/işlem kanıtı eksik**. Kapalı uygulamayı doğal sohbetten başlatma ve genel kaynak dosyası düzeltme ayrı, henüz uygulanmamış yeteneklerdir. Tüm bilgisayarı sınırsız kontrol ettiği iddia edilmez.
