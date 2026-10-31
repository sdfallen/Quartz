# WinError 740 ve yönetici uygulamaları

## Gerçek bulgu

Kullanıcının Antigravity/Codex değerlendirmeleri ThrottleStop başlatılırken tekrarlanan WinError740 gösteriyor. Gerçek dosya `C:\Users\LENAVO\Desktop\ThrottleStop.exe`; manifesti `requireAdministrator` içeriyor. Test süreci normal yetkide: integrity RID `0x2000`. EXE teşhis sırasında çalıştırılmadı. Manifest kanıtı `quartz-elevation-20261031/throttlestop-manifest.json` içinde.

Bu, Windows'un beklenen ayrıcalık sınırıdır. `CreateProcess` yönetici gerektiren bir programı normal token ile başlatmayı reddeder. Windows'un desteklediği UAC istemi `ShellExecute/runas` yoludur. Quartz'ın dosya/masaüstü Tam Yetki tercihi bir Windows yönetici token'ı değildir. Kaynak: [Microsoft UAC çalışma şekli](https://learn.microsoft.com/en-gb/windows-server/security/user-account-control/how-user-account-control-works), [Yönetici haklarıyla çalıştırma](https://learn.microsoft.com/en-us/windows/win32/secbp/running-with-administrator-privileges).

## Yeni akış

1. Normal EXE başlatmada 740 alınırsa uygulama yolu, dosya kimliği ve SHA-256 mevcut sınırlı launch profiliyle bağlanır. Shell/yorumlayıcı, sistem güvenlik araçları ve ASTER sınırları korunur.
2. Göreve bağlı `elevation` kartı oluşur. Normal Tam Yetki otomatik onayı bu kartı kapsamaz. Aynı hedef yeniden istendiğinde yeni Popen/UAC döngüsü oluşturulmaz.
3. Kullanıcı kartta **Windows UAC isteğini aç** seçerse aynı EXE tekrar doğrulanır. İş arka plan thread'ine alınır; görev kilidi UAC beklerken tutulmaz. OS istemini insan onaylar/reddeder; ajan bu pencereye tıklamaz ve parola girmez.
4. Yalnız doğrulanmış EXE, argümansız `runas` ile kendi klasöründe açılmaya çalışılır. Quartz veya bütün ajan ortamı yükseltilmez. Çift onay aynı isteği yeniden çalıştırmaz.
5. Windows dönüşü `launch_requested`, `cancelled` (1223) veya `failed` olarak kaydedilir. `launch_requested` pencere doğrulaması değildir. Yeni pencere/süreç otomatik sahiplenilmez; mevcut broker kontrolleri gerekir.
6. Süren/bitmiş CLI turları mevcut görev bağlamıyla devam eder. Var olan devam bütçesi dolmuşsa doğrulanmış başarı yerine açık sınır durumu verilir.
7. Stop sırasında Windows istemi zaten açıldıysa Quartz bunu otomatik kapatmaz. Kullanıcı Windows ekranında Hayır seçebilir. Geç dönen sonuç eski görevin kanıtına yazılır; yeni görev başlatılmaz, uygulama öldürülmez.

Dosya düzeyinde REA öğrenmesi için programı çalıştırmak veya yönetici olmak gerekmez; doğrulanmış hedef bu salt okunur yoldan da incelenir.

## UIPI sınırı

Yükseltilmiş bir programın açılabilmesi, normal Quartz'ın onu otomatik kontrol edebileceği anlamına gelmez. Native girişten önce Windows token integrity RID'leri sorgulanır. Hedef daha yüksekse veya seviye okunamıyorsa girdi reddedilir. Kaynak gözlemleri ve dosya incelemesi kullanılabilir; tam yönetici UI kontrolü bu değişiklikle sağlanmaz. Kaynak: [Microsoft UIAccess ve integrity kısıtları](https://learn.microsoft.com/en-us/windows/security/threat-protection/security-policy-settings/user-account-control-allow-uiaccess-applications-to-prompt-for-elevation-without-using-the-secure-desktop).

Registry, UAC, sürücü, güvenlik ayarı veya EXE manifesti değiştirilmedi. Donanım ayarları denenmedi. Programın kendi açılış davranışını Quartz garanti etmez; karttaki onay ajana ayar değiştirme talimatı değildir.

## Doğrulama ve sınırlar

- Gerçek ThrottleStop manifesti ve gerçek normal token RID sorgusu: VERIFIED, salt okunur.
- 740 sınıflandırma, tekrarlı launch engeli, açık onay, çift tıklama, değişen EXE reddi, 1223 iptali, Stop sonrası geç sonuç, doğru çalışma klasörü ve UIPI daha-yüksek/unknown/eşit testleri: kontrollü testler.
- GUI Tam Yetki seçiliyken UAC kartının kendiliğinden onaylanmaması ve prompting sırasında düğmenin kapalı olması: JS testi.
- Gerçek UAC onayı ve yükseltilmiş ThrottleStop UI'si: NOT TESTED; donanım uygulaması teşhis için çalıştırılmadı.
- Genel kısayol/URL başlatma yolları Windows Shell davranışını korur. Yeni 740 kartı, normal EXE/common-app/EXE arama ve açık EXE yolu akışını kapsar. Her olası shortcut/installer/broker senaryosu test edilmiş sayılmaz.
- İlk hedefli test komutunda olmayan bir test modülü adı kullanıldı; hata logu saklandı. Doğru test modülleriyle tekrar geçildi. Son tam test ve paket sonucu `build.log` içindedir.

Kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-elevation-20261031`. Tam kaynak checkpoint'i değişiklik öncesi alınmıştır. Çalışan kullanıcı uygulaması zorla kapatılmaz; güncelleme yalnız boşta güvenli kapatma akışıyla yapılır. Her olası hatanın önlendiği iddia edilmez.

Ek düzeltme: yeni bir Jarvis kontrol girişimi başladığında önceki görüntü/başarı kaydı geçersizleştirilir. Yeni işlem erişim/yükseltme hatası alsa bile eski doğrulanmış sonuç bu işlem için kullanılamaz. Yetkisiz ikinci ajanın kontrol isteği bu kaydı değiştirmeden reddedilir. `final-safe-tests.log`: 644 test PASS. İlk paket, son kaynak değişikliği derleme sırasında yapıldığı için kaynak/paket imza kontrolünde reddedildi; kurulmadı. `rebuild.log` ve `package-verification.json` sabit son kaynağın yeniden paketlenmesini kaydeder. Eski reddedilen aday kanıt için ayrı tutulmuştur.

## Son paket ve teslim doğrulaması

- Son tam regresyon: **647 test PASS**. `final-safe-tests-2.log` ve dağıtım öncesi bağımsız tekrar `regression-final.log`.
- Son sabit kaynak paketi: **52 kontrol PASS / 0 başarısız** (`verified-package.json`, son dağıtım `package-verification.json`). Önceki iki stale aday kurulmadı; yukarıdaki 644 test ara aşamadır.
- Kurulu EXE SHA-256: `1ee4ebcf14883b83b87f2a999c9b72b97f619708ec6a97898e5ebb44e9ce69ad`.
- Boşta olduğu doğrulanan eski Quartz normal Alt+F4 ile kapatıldı. Eski dağıtım geri alınabilir klasörde saklandı. Kaynak `.env`, bellek ve sohbet dosyaları doğrulama boyunca değişmedi; dağıtımdaki taşınan kullanıcı dosyalarının hash karşılaştırması eşit (`all_preserved_data_equal=true`).
- Yeni paket normal yetkiyle açıldı. Ana sohbet, geçmiş, Q simgesi ve Tam Yetki tercihi UIA ağacında mevcut; `installed-startup-uia.json`. Bu erişilebilirlik kanıtıdır, piksel tabanlı görsel QA değildir. Ekran yakalama zaman aşımı devam etti; koruma aşılmadı.
- Gerçek UAC kabul/ret ve yükseltilmiş uygulamanın UI kontrolü: **NOT TESTED**. ThrottleStop çalıştırılmadı. Sistem, sürücü, UAC, Overlay ve Warband dosyaları değiştirilmedi.
- Paket dağıtım makbuzu ve son kanıt özeti evidence kökündeki `final-receipt.json` içinde referanslanır.
