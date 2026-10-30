# Pencere odağını geri alma — 27 Ekim 2026

Kullanıcı kararı: izinli görevde başka pencereye odak geçmesi tek başına görevi sonlandırmasın. Tam Yetki ve mevcut otomatik kapsam onayı korunur.

## Değişiklik

- `core/desktop_agents.py`: eski görev giriş yolu da persistent_control kullanıyor. Ajanın "odak değişince tekrar deneme" talimatı kaldırıldı.
- `core/natural_desktop.py`: onaylanmış masaüstü kapsamı odak kurtarmayı kullanıyor; UM/Warband yolu değiştirilmedi. Yeni görüntüye göre devam etme talimatı eklendi.
- `core/desktop_broker.py`: odağı kaybeden doğru pencere yeniden doğrulanıp bir kez öne alınır. Eski snapshot geçersiz kılınır. Eski snapshot ile gelen eylem uygulanmadan yeni gözlem döndürülür (`action_skipped=true`). Ajan yeni görüntüye göre sonraki eylemi seçer.
- Odak alma başarısızlığı artık yutulmuyor. Girdi gönderilmeden açıklayıcı hata döner; yetkili görev açık kalır. Sonsuz odak döngüsü yoktur.
- Pencere kimliği değişirse, süre dolarsa veya Stop kullanılırsa yeniden kontrol başlamaz. Kilitli oturuma girdi gönderilmez.

## Doğrulama

Broker ve Jarvis hedefli testleri: 46/46 PASS. Tam regresyon ve paket çıktıları aşağıdaki kanıt klasöründe tutulur.

Yeni testler: odak kaybı → aynı grant → yeni gözlem → yeni eylem; başarısız odak → sıfır girdi; kilitli oturum; değişen PID; Stop sonrası yeniden odak almama. Önceki NaturalTask odak kaybında koşulsuz sonlanma testi yeni kullanıcı sözleşmesine güncellendi; düşük seviyede explicit persistent_control=False davranışı ayrı testte korunuyor.

Canlı eski Quartz UIA ekranında `blocked: foreground changed (user takeover)` görüldü. Codex ekran yakalama aracı iki güncel pencere denemesinde `window capture timed out: timed out waiting on channel` verdi. Gerçek Windows odak değiştirme kabulü henüz doğrulanmadı.

## Koruma ve teslim

Önceki dosyalar: `C:\Users\LENAVO\.codex\backups\quartz-focus-recovery-20261027\before-*.zip`. Ek olarak önceki NaturalTask testi ayrı yedeklendi.

Kullanıcının önceki kaynak değişiklikleri geri alınmadı. ASTER, kayıtlar, sistem ayarları ve güvenlik yapılandırması değiştirilmedi. Açık Quartz zorla kapatılmadı. Staged paket kurulu paket değildir; devreye alma sonucu deployment receipt ile ayrıca doğrulanmalıdır.

## Devreye alma sonucu

Kullanıcı Quartz'ı normal kapattı. Son regresyon: 481/481 PASS (61.225 saniye). Antigravity language_server.exe altında kalan QuartzDesktopMCP.exe eski klasörün toplu taşınmasını engelledi; bu süreçlere dokunulmadı. Paket karşılaştırmasıyla yalnız Quartz.exe ve _internal/base_library.zip değiştiği belirlendi. Bu iki dosya yedeklenerek değiştirildi, paketteki eksik runtime DLL dosyaları eklendi. MCP helper değişmedi.

Kurulu EXE SHA256: e454e55e939355890e119e3418437a06dbbab9b2e69e275ee64f3d10d350d2a1.
39 kullanıcı dosyası hash-equal. installed-verification.json içindeki bütün paket/kaynak kontrolleri PASS. deployment-receipt.json hedefli dağıtımı kaydeder. Quartz yeni süreçte açıldı, UIA ana sohbeti, geçmişi ve Tam Yetki durumunu doğruladı. Bu açılış kanıtı, gerçek odak değiştirme kabulünün yerine geçmez; o test henüz LIVE VERIFIED değildir.
