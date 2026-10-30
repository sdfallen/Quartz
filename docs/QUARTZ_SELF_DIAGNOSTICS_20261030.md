# REA destekli Quartz öz teşhis — 30 Ekim 2026

## Kapsam ve sorumluluklar

Codex: `core/self_diagnostics.py`, `core/rea_adapter.py`, backend IPC, isteğe bağlı araç hazırlığı ve paket doğrulaması. Antigravity: sohbet içi kart, GUI sarmalayıcıları, CSS, frontend testleri. Ortak sözleşme: `SELF_DIAGNOSTICS_CONTRACT.md`.

İlk dilim yalnız Quartz'ın kendi paketini inceler. Otomatik onarım, başka uygulama/oyun araştırması veya genel bilgisayar yetkisi eklenmedi. Üretim IPC'si hedef dosya, klasör veya komut kabul etmez. Kullanıcı verileri/anahtarları okunmaz. Hedef EXE analiz amacıyla çalıştırılmaz. Rapor ve REA geçici kanıtları inceleme hedefinden ayrı dizinlerde yazılır.

## Uygulama

- Tek arka plan işi; başlat/durum/iptal; sınırlı iş geçmişi. İkinci aktif başlatma aynı işi döndürür. İşin `completed` olması kontrollerin geçtiği anlamına gelmez; ayrı `verdict` alanı vardır.
- Gerekli bileşenler ve release manifestindeki SHA-256 değerleri karşılaştırılır. Manifest yokluğu NOT_TESTED; eksik veya farklı dosya FAIL; tamamlanamayan inceleme UNKNOWN olarak kalır. Başarılı manifest karşılaştırması güvenilir yayıncı kimliğini kanıtlamaz.
- Manifest yolları bütün olarak doğrulanmadan referans dosyalar okunmaz. Dış yol, özel veri dosyası ve sembolik/junction yolları reddedilir. Dosya/süre/boyut sınırları ve iptal kontrolleri vardır.
- REA 6.8.0 adaptörü yalnız `inspect-artifact` statik yolunu çağırır. Hedef hash'i, PyInstaller biçimi, kaynak kapsamı ve sayısal bütünlük sonuçları doğrulanır. Exit0 veya `success:true` tek başına PASS değildir.
- REA stdout/stderr ve tam kanıt dosyası kullanıcı sohbetine aktarılmaz. Kalıcı rapor doğrulanmış alanları ve hedef/çıktı/kanıt hash'lerini taşır. Tam kanıt dosyası özel geçici klasörde temizlenir.
- Mevcut IPC süreç kimlik doğrulaması korunur. Çocuk süreçten hesap anahtarları ve masaüstü token'ları çıkarılır. İptal yalnız başlatılan sürecin kendi ağacını sonlandırır.
- İsteğe bağlı `scripts/prepare_rea_tool.py`: sabit sürüm, özel Node, `--ignore-scripts`, engine denetimi, sürüm kontrolü ve atomik araç tanımı. Global npm/PATH veya ajan MCP ayarları değiştirilmez. Normal teşhis başlatılması otomatik indirme yapmaz.
- REA ana Quartz paketine gömülmez; eksikse mevcut yerel kontroller devam eder ve kapsam PARTIAL kalır.

## Gerçek kanıtlar

Kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-self-diagnostics-20261030`.

| Test | Sonuç | Kanıt |
|---|---|---|
| Node uyumluluğu | Sistem Node 26.7.0 reddedildi; sistem değiştirilmedi. Özel 26.13.0 kullanıldı | `rea-install.log`, `rea-install-compatible-node.log` |
| Gerçek REA kurulumu | npm 6.8.0, 176 paket, kurulum scriptleri kapalı | Aynı dosyalar, `optional-tool-receipt.json` |
| İlk gerçek CLI denemesi | FAILED: summary için `--evidence_output` zorunluydu. Tekrarlanan kör çağrı yapılmadı; komut düzeltildi | `rea-real-summary.json` |
| Düzeltilmiş gerçek CLI | PASS, PyInstaller / Python 3.13, 17 arşiv girdisi | `rea-real-summary-v2.json` |
| Gerçek servis + gerçek paket | PASS, 1.917 dosya / 154.302.868 byte eşleşti; REA 3.756 üye hash'i; çelişki0 | `real-service-result.json` |
| Gerçek yerel TCP IPC | Yetkisiz ve dış hedef istekleri reddedildi; ikinci start tek iş; hedef değişmedi | `real-ipc/acceptance.json` |
| IPC gecikmeleri | Başlatma147,129ms; 149 sorgu; medyan33,144ms; en yüksek188,140ms | Aynı dosya |
| Gerçek REA iptali | cancelled; 0,052s; kalan kendi süreç0; hedef değişmedi; tamamlanmış başarı raporu yazılmadı | `real-cancel.json` |

Yukarıdaki servis/IPC testlerinin hedefi kabul edilmiş 29 Ekim dağıtım EXE'sidir:
`5f0609722c7732807617873f25f6573005f1f423bc9f63671966a9b37a4c818c`.
Bunlar yeni teşhis çekirdeğinin gerçek araca bağlandığını gösterir. Yeni EXE'nin ana sohbetinden yapılmış canlı kabul olarak sunulmaz. Süreler bu makinedeki tekil ölçümlerdir; düşük donanım veya genel gecikme garantisi değildir.

## Karşılaşılan kurulum ayrıntısı

Windows Store Python, AppData dosyalarını fiziksel cache yolu üzerinden gösterebilir. Araç tanımı yol kontrolünde gevşek metin eşleştirmesi yerine gerçek dosya kimliği (`samefile`) ve kayıtlı script hash'i birlikte kullanılır. Aynı dosyanın sanallaştırılmış ve normal yolu kabul edilebilir; değiştirilmiş script veya bozuk makbuz otomatik fallback ile çalıştırılmaz. Native EXE için ayrı gerçek per-user araç konumu da hazırlanmıştır.

## Koruma ve kabul sınırı

Dokuz kaynak/kurulu kullanıcı veri dosyası ilk kontrolde diff0. Mevcut çalışma EXE'si ve önceki dağıtım arşivleri korunur. ASTER/Warband'a erişilmedi; model/hesap bağlantıları değiştirilmedi. Düşük donanım algoritmaları Codex tarafından düzenlenmedi.

Frontend kaynak/JS testleri gerçek paketlenmiş sohbet kabulünden ayrıdır. Yeni paket için görsel test, başlat/iptal ve sohbet kartı kabulü ayrıca kaydedilmelidir. Son build/paket kontrolü aynı kanıt kökündeki `build.log` ve teslim makbuzuna bağlanır.

Kullanılabilecek mevcut sohbet komutları: `Öz teşhis başlat`, `REA olmadan öz teşhis başlat`, `Öz teşhisi durdur`. Genel `Quartz'ı kontrol et` ifadesinin de aynı yerel akışa güvenilir bağlanması frontend kapsamındaki sonraki dar kontroldür; sözcük yakalama başarısı model/GUI kabulünün yerine geçmez.

## Son teslim durumu

- Tam regresyon: **607 PASS** (`regression-final-v2.log`). Sonrasında yalnız sentetik frontend test verisi, gerçek API anahtar biçimini taklit etmeyen `fixture-private-value` ile değiştirildi ve aynı değerin gizlendiğini doğrulayan assertion güncellendi; bu dosyanın **7/7** testi tekrar geçti (`ui-fixture-final.log`). Üretim GUI'sine Codex değişikliği yapılmadı. Yayın denetimi gevşetilmedi: **275 kaynak dosyası + 286 geçmiş blob, sıfır bulgu** (`publication-final.json`).
- Yeni aday paket: **47/47 kaynak/paket kontrolü PASS**, temiz dağıtım denetimi **1.918 dosya, sıfır bulgu**.
- Aday EXE SHA-256: `fbef54c7f6f25d1d497e7c14ad67e0af2fe7aae4cc2170dedb25d8f6321c7a52`.
- Temiz aday: `C:\Users\LENAVO\.codex\backups\quartz-self-diagnostics-20261030\clean-candidate\Quartz`.
- **Paketlenmiş GUI açılışı / sohbet / Öz Teşhis düğmesi: UIA VERIFIED.** `gui-test/initial-uia.txt`.
- **Görsel QA: BLOCKED.** Ekran yakalama zaman aşımı; screenshot kanıtı yok.
- **Gerçek ana sohbet → gönder → kart → sonuç: BLOCKED / NOT TESTED.** Tıklama `coordinate input geometry is unavailable` ile engellendi. Desteklenen UIA `set_value` ile test komutu gerçekten sohbet alanına yazılabildi; fakat güvenilir odak/Gönder kontrolü doğrulanamadığından gönderim yapılmadı. Belirsiz odakla Return veya rastgele koordinat kullanılmadı. `gui-test/input-set-uia.txt`, `gui-test/acceptance.json`.
- İki izole GUI test kopyası **Alt+F4 ile normal kapandı**; çalışan test Quartz süreci kalmadı. Hiçbir normal kullanıcı oturumu kapatılmadı. Çalışan yerel EXE dağıtımı değiştirilmedi; aday ayrı tutuluyor.

Teşhis kartı ve backend sözleşmesi kaynakta birleşmiş durumda. Son insan/aktif masaüstü kabulü: aday ana sohbetinde `Öz teşhis başlat` gönderilmesi, gerçek ilerleme ve kapsamın görülmesi, `Öz teşhisi durdur` ile iptal ve sonrasında yeni bir işin tamamlanması. Bu kabul henüz gerçekleşmiş sayılmaz. Statik PASS bütün uygulamanın hatasızlığı veya otomatik onarım başarısı değildir.

## Resmî kaynak

[REA PyInstaller kapsamı ve kanıt sınırları](https://github.com/morluto/rea/blob/main/docs/python-packaged-applications.md). Paket adı `rea-agents`; incelenen/pinlenen sürüm6.8.0. MIT ve üçüncü taraf lisans bildirimleri isteğe bağlı npm kurulumu içinde korunur.
