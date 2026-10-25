# Yetki seçimi düzeltmesi — 25 Ekim 2026

## Kanıtlanan neden

Kurulu uygulamada seçim `Tam Yetki` görünmesine rağmen son iki görev girişimi
`conversation_only` yolundan çalışmıştı. Gerçek kullanıcı mesajlarındaki
`kontrol edin` ve `başlayın`, niyet sınıflandırıcısının eylem kalıplarında yoktu.
Bu yol bilerek araçları ve yazma izinlerini kapatıyordu. Yanıtlar tamamlanmış,
`natural_task` boştu; masaüstü/Universal Modder görevi hiç başlamamıştı.

Bu bulgu, Natural akışının her zaman seçili dosya yetkisiyle çalışması gerektiği
anlamına gelmez. Natural, salt okunur CLI içinde kapsamı onaylanmış MCP araçları
kullanır. Dosya modu ve masaüstü/UM kapsam onayı farklı yetkilerdir.

## Değişiklik

- Türkçe çoğul emirler görev olarak algılanır; açıklama ve alıntılar sohbet kalır.
- Gönderilen mesajın yetki seçimi, asenkron yönlendirmeden önce sabitlenir.
- Seçili ve etkin mod ayrı metadata alanlarında kaydedilir; ajana host bağlamıyla
  bildirilir. Salt sohbet, Tam Yetki seçiliyken de araçsız kalır.
- Yetki sorgusu Quartz tarafından gerçek seçili modla yanıtlanır; ajan tahminine
  bırakılmaz ve bu sorgu kendisi bir bilgisayar görevi başlatmaz.
- Normal dosya görevleri mevcut checkpoint/onay/yazma kilidi yolunu kullanır.
- Natural görevler seçimi ve sınırlı önceki konuşma bağlamını alır. Bu bağlam
  güvenilmeyen veri olarak işaretlenir ve hiçbir yeni izin vermez.
- Menü değişikliği anında kısa durum yazısını günceller. Çalışan bir CLI sürecinin
  yetkisi geriye dönük değiştirilmez; seçim sonraki dosya görevine uygulanır.
- Masaüstü, UM, IPC kimlik doğrulaması, Stop ve korunan proje kontrolleri korunur.

## Doğrulama

| Düzey | Sonuç |
| --- | --- |
| Birim/regresyon | 460 test; 458 başarılı, 2 önceden kayıtlı beklenen hata |
| JavaScript | Gömülü JS parse exit 0; gerçek fonksiyonları kullanan VM testleri başarılı |
| Gerçek Codex / proje yazıcısı | `gpt-6-luna`, düşük çaba; ana sohbet servisi üzerinden geçici aritmetik projesi düzeltildi |
| Aynı sohbette mod değişimi | İlk tur `read-only`, ikinci tur `workspace-write`; ilk tur kaynak değişmedi, ikinci tur hata düzeltildi |
| Checkpoint/sonuç/kilit | Checkpoint complete; test dosyası değişmedi; host tarafından çalıştırılan 2 test başarılı; kalıcı sonuç ve kilit bırakma doğrulandı |
| Paketli GUI görsel kabulü | Ekran yakalama iki kez `window capture timed out`; görsel kabul verilmedi |
| Paketli GUI erişilebilirlik | Yeni EXE açıldı; çevrimiçi durum, eski sohbet, kayıtlı modeller ve yeni yetki bildirimi gerçek UIA verisinde görüldü |
| Paketli GUI girdi kabulü | Giriş alanını seçme `coordinate input geometry is unavailable` ile engellendi; mesaj gönderilmedi, izin menüsü otomatik değiştirilmedi |

İlk canlı probe, tamamlanan turun `run_id` alanının bilerek temizlenmesini
yanlışlıkla dispatch eksikliği saydı. Probe, kalıcı `run_ids` listesini okuyacak
şekilde düzeltildi; bu üretim ajan kodu hatası değildi. İlk tam regresyon sırasında
yetki sorgusu mevcut masaüstü yardım cümlesini de yakaladı; açık masaüstü/ekran
ifadeleri yardım yolunda kalacak şekilde daraltıldı ve regresyon geçti.

Yerel, Git dışında tutulan gerçek CLI kanıtları:

- `labs/permission-chat-writer-20261025-141158/result.json`
- `labs/permission-chat-switch-20261025-141446/result.json`

Bunlar paketli GUI'de açılır menü kullanımının veya canlı UM kontrolünün kabulü
değildir. Tam Yetki'nin gerçek sınırsız dosya erişimi bu görevde kullanıcı verileri
üzerinde denenmedi; taşıma ve izin korumaları regresyon testleriyle denetlendi.

## Koruma / teslim

Değişiklik öncesi checkpoint:
`C:\Users\LENAVO\.codex\backups\quartz-permission-mode-20261025\agent-1792925778-9d7b75f82c584aeba1593ff1fff16c47.zip`

Paket ve veri koruma makbuzu:
`C:\Users\LENAVO\.codex\backups\quartz-permission-package-20261025\deployment-receipt.json`

Kullanıcı yalnız boşta yeniden başlatmaya izin verdi. Son Codex/Antigravity
mesajlarının `completed` olduğu ve UI'da `Normal sohbet` durumu görüldükten sonra
Quartz normal Alt+F4 ile kapatıldı. Sohbet dosyası kapanışta değişmedi. ASTER,
Warband ve kayıtları üzerinde işlem yapılmadı. Harici API anahtarına geçilmedi.

Kısa kullanıcı kontrolü: İstenen dosya modunu seçip `Yetkileriniz nedir?` yazın;
Quartz seçimi göstermeli. Ardından somut dosya görevini verin. Masaüstü/UM işi
gerekiyorsa kendi kapsam onayı sohbet içinde istenir. Çalışan bir görevi yeni
modla yürütmek için önce güvenli biçimde durdurup yeni görev olarak gönderin.

Teslim edilen EXE SHA256:
`4d176d4f9a27bf9eacf9c57c36849c523482cc360339b4696c69bd979f708d20`.
Kaynak/paket kod imzaları, helper protokolü, CSS ve Q ikonları eşleşti.
Kurulum öncesi son 460 test tekrar başarılı oldu (2 beklenen hata).
Eski dağıtım `C:\Users\LENAVO\.codex\backups\quartz-before-desktop-bridge-20261025-141913`
altında korundu. Yeni dağıtımla karşılaştırılan 32 veri dosyasında fark sıfır;
`preservation-deep.json` ve `deployment-receipt.json` bunu kaydeder.
UIA kanıtı `labs/permission-mode-20261025/deployed-uia.txt` dosyasındadır.
Güncel EXE normal biçimde açıldı; yalnız arayüz yüklenmesi doğrulandı. Gerçek
açılır menü etkileşimi ve ana sohbette yeni görev kabulü bu oturumda BLOCKED.
