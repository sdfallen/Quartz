# Quartz Tcl kapanması — 31 Ekim 2026

## Gerçek bulgu

Windows Application olayları 1000/1001, 14:38:29 kapanmasını doğruluyor. Hatalı modül `tcl86t.dll` 8.6.2.15, exception `0x80000003`, modül uzaklığı `0xfee74`. Etkilenen PID14836; kullanıcı daha sonra PID1368 ile yeniden açtı. Çalışan kullanıcı süreci teşhis sırasında kapatılmadı.

`Quartz.exe.14836.dmp` korundu. Dump exception thread1948; yığın belleğinde Tcl adresleri `Tcl_Panic+0x22`, `Tcl_DeleteInterp+0xf3`, `Tcl_AsyncDelete+0x106` ile eşleşiyor; `_tkinter.pyd` adresi de var. Bunlar ham yığın adresi eşleştirmeleridir, sembollü tam unwind değildir. `Tcl_AsyncDelete` thread sahipliği/destructor yolu ve kaynakta worker thread içinde oluşturulan Tk HUD, aynı hata sınıfına işaret ediyor. REA öğrenme dosyasında bir exception kanıtı bulunmadı; tüm kapanmaların aynı nedenden olduğu varsayılmadı.

## Düzeltme

Ekran kontrol göstergesinin Tk arayüzü, Quartz ana sürecinden ayrı bir yardımcı sürece taşındı. Tk yalnız yardımcı sürecin ana thread'inde oluşturuluyor. Normal uygulama bu gösterge için Tk interpreter oluşturmaz. Mevcut kenar göstergesi ve Görevi Durdur düğmesi korunur.

Yardımcı yalnız inherited stdin/stdout üzerinden sınırlı `show`, `label`, `hide` mesajlarını alır ve `STOP` bildirir. Dosya/komut/hesap işlemi kabul etmez; yeni socket, DLL injection veya runtime yoktur. PyInstaller windowed modunda None olan `sys.stdin/stdout`, yalnız işletim sisteminin devralınmış pipe handle'larından açılır. Özel `--quartz-overlay` giriş yolu backend/WebView2/hesap başlatmadan çıkar.

Ana süreç hide sonrasında eski yardımcıdan gelen olayları yeni göreve uygulamaz. Yardımcı beklenmedik biçimde kapanırsa görev Stop callback'i çalışır; ana uygulama kapanmaz. Ana süreç sonlanırsa pipe EOF'u yardımcıyı kapatır. Bu izolasyonun amacı native Tcl abort'unun tüm Quartz'ı düşürmesini önlemektir; tüm uygulama crash nedenlerinin giderildiği iddiası değildir.

## Doğrulama

Kanıt kökü: `C:\Users\LENAVO\.codex\backups\quartz-tcl-crash-20261031`.

- `real-overlay-isolation.json`: gerçek source yardımcı süreci normal hide ile exit0; görev yanlışlıkla durmadı. Ayrı ikinci yardımcı zorla sonlandırıldığında host hayatta kaldı ve görev Stop callback'i geldi. Host'ta `_tkinter` yüklenmedi. Bu, tam paketli masaüstü görev kabulü değildir.
- `tests/test_screen_overlay.py`: parent'ta Tk çalıştırılmaması, tekrar show sırasında tek helper, helper çöküşünde Stop, eski helper'ın yeni görevi bozmaması.
- `build.log`: konsolsuz EXE pipe ayrıntısı fark edilince durdurulan ilk derleme; silinmedi.
- `build-final.log`: düzeltilmiş son derleme ve tam test sonucu.
- Dump özel yedekte tutulur; ham dump kaynak deposuna/yayına eklenmez.

Paketli helper pipe/lifecycle testi ve gerçek görev aç/kapat regresyonu ayrıca raporlanmalıdır. Kullanıcı uygulaması açıkken dağıtım yapılmaz.

Son paket testi: `frozen-overlay-isolation.json` konsolsuz paketli EXE'nin inherited pipe üzerinden show isteğini alıp açık kaldığını, hide sonrasında exit0 verdiğini ve host'un hayatta kaldığını doğruladı. Tk/gösterge için yeni bir runtime yüklenmedi. Tam test sayısı 634; paket/source/helper/Q kontrolleri PASS. Açık kullanıcı penceresi Normal sohbet ve boş mesaj alanıyla doğrulandı, önceki boşta güvenli yeniden başlatma yetkisi kapsamında Alt+F4 ile normal kapatıldı. Dağıtım eski klasörün yedeğini ve veri hash karşılaştırmasını üretir.
