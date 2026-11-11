# Üçlü teslim incelemesi — 2026-11-01

Başlangıç: Codex 001c979 (sohbet kimlik sınırı). Antigravity 3a14401 ayrı
dalından, Claude 7e3270b Claude Outputs bundle'ından alındı. İnceleme dalı
codex/pyramid-delivery-review-20261101. Orijinal teslim dalları değiştirilmedi.

## Kabul edilen dilimler

- Claude: HTML gövdesi ui/shell.py içine ayrıldı. Başlangıç 047fa6e ile
  _HTML_BODY ve üretilen tam HTML bayt eşitliği yerelde tekrar doğrulandı.
  Sonuç frontend-equivalence.json. GUI servis sahipliği henüz taşınmadı;
  bütün frontend mimarisi tamamlandı denmez.
- Antigravity: runtime olay/timeout gözetimi ve başarısız probe cache'i
  kaynak incelemesine alındı. Teslimin önemli cleanup açıklıkları bulundu;
  aşağıdaki düzeltmelerden önce doğrudan dağıtım kabul edilmedi.

## Yeniden üretilen ve düzeltilen

1. Process-tree bool sonucu yalnız parent exit'e bakıyordu. Sağ kalan child
   varken True döndüğü fake psutil regresyonuyla üretildi. Artık bilinen
   child kimlikleri korunur; root öldükten sonra PID tahminiyle yeniden
   oluşturulmadan aynı psutil nesneleri üzerinden yeniden kontrol edilir.
2. İki runtime timeout/ikinci wait başarısızlığında canlı süreci ve writer
   kaydını finally içinde siliyordu. İki ayrı provider regresyonu bunu
   gösterdi. Mevcut watcher, exit doğrulanana kadar cancelling/cleanup_pending
   tutar; process/writer kaydı erken bırakılmaz. Sonradan doğrulanmış çıkış
   geldiğinde doğru terminal geçiş ve kilit temizliği yapılır.
3. Terminal stdout mesajı sonucu korusa bile session/thread kimliğini
   değiştirebiliyordu. İki provider için yeniden üretildi; terminal stdout
   artık yeni kimlik/olay eklemez.
4. shutdown, iptal isteğinden sonra canlı owned süreç kalmasını sessizce
   başarı saymamalı. Artık belirsizlikte hata bildirir. UI Stop ile gerçek
   süreç exit'i ayrı kanıt olarak tutulur.
5. Codex'e yeni örtülü 10 dakika deadline eklemek eski çağrı davranışını
   değiştiriyordu. Deadline opt-in yapıldı (default None); açık timeout'ta
   boolean/non-finite/negatif/geçersiz giriş reddedilir.
6. Claude IR-1 doğrulandı: JS betiği ana script bulunmasa da arşiv Notion
   script'ini parse edip geçebiliyordu. Şimdi tek, anlamlı ana script
   zorunlu; eksik/küçük/çoklu/bozuk blok non-zero döner. Arşiv Notion script'i
   çalışan GUI kontrolünün yerine kullanılmaz.
7. Paket kaynak doğrulamasına ui.shell/document/styles/theme eklendi.

İlk üç bulgu için önce başarısız regresyon kaydı saklandı. Testler gerçek
kullanıcı süreçlerine hasar vermeyen kontrollü süreç fixture'larıdır.
Bunlar gerçek model/masaüstü görevinin uçtan uca kabulü değildir.

## Ölçüm ve rapor düzeltmeleri

Antigravity benchmark'ında boş sahte codex.exe ve sentetik Python parent/child
kullanılmış. Ölçülen OS sayıları gerçek olsa da Quartz GUI veya gerçek CLI
ajan performansı değildir. Betik etiketi SYNTHETIC_PROCESS_MEASURED yapıldı;
ürün FPS/RAM/CPU iyileşmesi iddia edilmiyor. Orijinal rapor tarihsel kanıttır.
Orijinal rollback bölümündeki branch silme komutu, birleşmiş kodu geri almaz.
O komut uygulanmadı; entegre düzeltmeler için commit revert ve eski paket
yedeği kullanılacak. Kabul edilmiş arşivler silinmez.

## Doğrulama ve kalan sınır

İlk birleşik hedefli grup 71 test OK. Terminal kimlik ve shutdown retleri
eklendiğinde hedefli grup 73 test OK. Son süreç retry regresyonuyla inceleme
modülü 7 test OK. Önceki full-suite 866 case / 12 skip, son eklerden önceydi;
nihai build koşusunun sonucu ayrıca kaydedilecek. JS OK; Python syntax 239.

Yerel kanıt klasörü Codex backups/quartz-pyramid-review-20261101:
before.log, late-output-before.log, runtime-after.log, targeted-final.log,
review-final.log, frontend-equivalence.json, full-suite.log, build.log.

Watcher'ın beklenmeyen OS/izleme hatasında sahiplik korunur; otomatik olarak
writer/grant diriltilmez. Böyle bir belirsizlikte manuel recovery audit'i
gerekebilir. Tüm mimari ve bütün cleanup/restart edge-case'leri tamamlandı
denmez. P1 ortak task/run/Stop sözleşmesi, servis sahipliği ve kapanış
kompozisyonu sonraki dar dilimlerdir. ASTER ve Notion ajanı açılmadı.

Bu rapor paket/live sonucu gelene kadar SOURCE/TESTED kabulüdür. Eski
Notion'sız kurulum veya kullanıcı verisi bu kaynak incelemesinde değiştirilmedi.

## Son paket ve yerel devreye alma

- Son build koşusu: 868 test case OK, 12 helper önkoşul skip. Eklenen son
  orphan retry testi ayrıca 7 testlik review modülünde geçti; tam suite
  sayısı buna göre geriye dönük artırılmadı. Helper derlendikten sonra
  gerçek yerel koordinasyon modülü ayrıca 22 test / skip0 geçti.
- Paket 20261101-203956 derlendi; kaynak bytecode (runtime/process-tree/UI),
  helper, kaynaklar ve Q ikon kontrolleri geçti.
- Gerçek hesaplarla iki CLI protokol smoke'u (geçici klasör, araç guard'ı):
  Codex ve Google ajanı istenen metni döndürdü, exit0 ve
  process_exit_confirmed=true. Codex errors listesinde 4, Google tarafında
  1 tanı kaydı vardı; bunlar sınıflandırılmadı, tamamen uyarısız koşu
  iddiası yok. GUI/proje yazma/masaüstü kontrolü kabulü değildir.
- Quartz'ın kapalı olduğu doğrulandı. Önceki Notion'sız paket korundu:
  Codex backups/quartz-before-pyramid-integration-20261101T174713Z.
  Yeni EXE hash: 2462ad3d4728bdc43f0bf963019ee754a59b54bcb9e04a58bc8070b8d7044fce.
- 43 kullanıcı dosyası kopyalama sonrası hash eşitliğini korudu. Açılıştan
  sonra .env, memory, conversations, projects, mobile_access 5/5 aynı.
- Gerçek paket açıldı; UIA'da Q, online, Codex/Antigravity/Birlikte,
  mesaj alanı ve Gönder var; Notion ajanı yok. Pixel QA bu koşuda yapılmadı.
- Yeni kullanıcı görevi/mesajı paketli sohbete gönderilmedi. Tam ana sohbet
  → gerçek yazma/desktop → ek talimat → Stop → restart kabulü hâlâ açık.

Kanıtlar: build.log, coordination-after-helper.log, live-cli-smoke.json,
provider-probes.json, deployment.json, live-ui-accessibility.json,
postlaunch-protection.json. Yeni uygulama açık bırakıldı. Bu ilk birleşik
dilimlerdir; sistem piramidinin bütünü tamamlandı ilan edilmiyor.
