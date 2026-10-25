# Bağımsız incelemenin entegrasyon kararı

Bu tablo ilk dilimin tarihsel kararlarını anlatır. İkinci dilimde F01 dil kapsamı
genişletilip iki expectedFailure ve iki eski-hata assertion'ı doğru davranış
regresyonuna dönüştürüldü; güncel durum `FOLLOWUP_20261025.md` içinde. Özgün
Antigravity rapor dosyaları değiştirilmedi. Güncel tam koşuda 3 expectedFailure
kalır; bunlar otomatik olarak kritik ürün kusuru diye yorumlanmaz.

Antigravity'nin dosyaları `docs/reliability/antigravity/` altında özgün teslim
olarak tutulur. Üretim dosyalarını kendisi değiştirmedi. Ana geliştirici aşağıdaki
kararları kaynak ve bağımsız testlerle verdi; rapordaki her öneri zorunlu sözleşme
veya kanıtlanmış ürün hatası olarak otomatik kabul edilmedi.

| Bulgu | Karar |
|---|---|
| F-01 kibar/İngilizce komutlar | Gerçek kapsam boşluğu; bu çekirdek diliminde niyet kuralları değiştirilmedi. Salt sohbet varsayılanı ve izin sınırları korundu. Ayrı dil/false-positive corpus'u ile ele alınmalı. `misiniz` önek eşleşmesi ilk rapordaki iddiadan farklı; sonraki test düzeltilmiş. |
| F-02 aynı task nesnesini yeniden başlatma | Mevcut API tek kullanımlı nesne yaratıyor. Job'u temizlemek tek başına token, thread, cache, HTTP ve izin durumunu sıfırlamaz. Yeni görev = yeni task nesnesi sınırı korunur; bu bir singleton yeniden kullanım sözleşmesi değildir. |
| F-03 log izninde input iptali | Kabul edildi ve düzeltildi. Yalnız değişmeyen onaylı pencere kimliklerinde log-only istek mevcut lease'i korur; yeni log onaydan önce okunamaz. Yeni pencere/süreç kimliği eski input'u iptal etmeye devam eder. Log onayı input lease süresini uzatmaz. |
| F-04 kopan socket/header | Kabul edildi ve düzeltildi. Header + body yazımı kopma koruması içinde. Bağımsız test de geçti. |
| F-05 tek progress alanı | `_set_turn_progress` zaten RLock altında, UI bütün `messages` listesini render ediyor. Skalar son-ilerleme etiketi tek başına balon kaybını kanıtlamaz. Agent-keyed progress yararlı ek kalite hedefidir; bu dilimde gerçek nesil/callback yarışları önceliklendirildi. |
| F-06 boşta devam | Aktif araç görevi yokken devam metni geçmişiyle araçsız konuşmaya gider; kendiliğinden eski izinleri canlandırmaz. Evrensel sabit ret, normal sohbetin devamını bozabileceğinden eklenmedi. |
| F-07 model iddiası/kanıt | Pasif, boyut ve proje sınırları olan Python AST kontrolü eklendi. `SOURCE/STATIC` ile `LIVE` ayrılır. Bilinmeyen proje testlerini otomatik çalıştırmak güvenli olmadığı için yapılmaz. |
| F-08 üç katman | Tek seferde birleştirilmedi. Natural task görev sahibi, DesktopAgent legacy adaptör, broker tek input otoritesi olarak kaldı. Paylaşılan sonuç ve bağımsız cleanup sözlüğü ayrıldı. |
| F-09 polling | Yavaş provider/Squad kontrolleri single-flight arka plan snapshot'ına alındı; chat poll için tarayıcıda üst üste bindirmeme koruması eklendi. Ölçülmemiş FPS/CPU kazancı iddia edilmedi. |
| F-10 İngilizce kapanış nedeni | Ana metin Türkçeleştirildi. Tam teknik neden açılır ayrıntılarda ve kanıt dosyasında korunur. Bütün event içinde teknik metni yasaklayan önerilen test bu ayrımı karşılamıyor. |

Bağımsız paketteki beş `expectedFailure`, beş zorunlu üretim hatasının açık
kaldığı anlamına gelmez. İkisi dil kapsamı, biri tek kullanımlı nesneyi yeniden
kullanma önerisi, biri ek ilerleme görünümü, biri teknik ayrıntıları da yasaklayan
sunum önerisidir. Değiştirilmeyen inceleme testlerinin kapsamı final raporda ayrı
belirtilir; bunlar geçmişten gelen otomatik LIVE kabul değildir.
