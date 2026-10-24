# Yetki ve checkpoint düzeltmesi — 20 Ekim 2026

## Davranış sözleşmesi

- Varsayılan sohbet yetkisi salt-okunur. Yazma seçimi görev başında açık onay
  gerektirir; backend kendi kendine `confirm_write=True` üretmez. Proje/tam yetki
  bilgisi IPC → sohbet → runtime boyunca ayrı taşınır. Açık salt-okunur seçimi
  eski `write` bayrağından önceliklidir.
- Codex proje yazması `workspace-write`/otomatik onay incelemesini, açık tam yetki
  ise ayrı full-access yolunu kullanır. Tam yetki proje yalıtımı değildir.
- Antigravity Windows adaptöründe proje-sınırlı yazma güvenliği doğrulanmadığı
  için bu mod REDDEDİLİR, tam yetkiye çevrilmez. Açık tam yetki kullanılabilir.
  İnceleme modu da mutlak işletim sistemi salt-okunur yalıtımı olarak sunulmaz.
- İzin reddinde yetki artırma veya yazmalı işi otomatik yeniden yürütme yok.
  Yalnız eski salt-okunur oturum, izin/model/kota hatası değilse aynı kısıtlarla
  bir kez yeniden denenebilir. İç `TypeError` ikinci dispatch'e dönüşmez.
- Sohbet ve normal görev yazıcıları aynı `_start_writer` yolunu kullanır.
  Aynı/iç içe proje yazıcıları çakışamaz. Tam yetki yazıcısı diğer tüm yazıcılarla
  karşılıklı dışlanır. Bunlar Quartz servisindeki kilitlerdir; uygulama dışındaki
  editör/CLI süreçlerini işletim sistemi seviyesinde kilitlemez.
- Birlikte modunda yazmalı görev: Codex tek yazıcı → tamamlanınca Antigravity
  salt-okunur inceleme → karşılıklı salt-okunur değerlendirme. Salt-okunur iki
  ajan görüşmesi paralel kalır. Başarısız yazıcı, başarılı inceleme sayesinde
  tamamlanmış sayılmaz. Tek ajana yönlendirilmiş görev kendi izinlerini korur.

## Checkpoint kapsamı

Her servis yazıcısından önce doğrulanmış proje arşivi gerekir. Hata, eksik arşiv
veya tamamlanmamış checkpoint varsa runtime BAŞLAMAZ ve kilit bırakılır.

Git projesinde mevcut değişiklikler non-destructive Git ref'iyle ve izlenmeyenler
dahil tracked/nonignored dosyalar ZIP ile korunur. Git dışı projelerde sınırlı
dosya arşivi kullanılır. Arşiv proje dışında `~/.quartz/checkpoints/` altında
oluşur. SHA256 dosya manifesti, silinmiş tracked dosya bilgisi ve CRC kontrolü
vardır. Değişim sırasında okunan dosya, güvensiz yol veya dosya/boyut sınırı
yazmayı durdurur. `.partial`, yalnız doğrulama sonrasında `.zip` olur.

**Bu tüm bilgisayarın yedeği değildir.** Git-ignored dosyalar, Git dışı projelerde
gizli/runtime/cache çıktıları, kurulu oyun modülü, dış kayıtlar, ortak ayarlar ve
tam yetkiyle proje dışında değiştirilebilecek dosyalar bu arşive dahil sayılmaz.
Otomatik yıkıcı geri yükleme eklenmedi. `C:\WarbandIsland` kayıt engeli korundu;
Universal Modder/ASTER entegrasyonu veya yeni save izni verilmiş sayılmaz.

## Doğrulama

Komut: `python -B scripts/run_safe_tests.py`.
Runner test sürecinin log ve hafıza yollarını discovery öncesinde geçici klasöre
taşır; gerçek uygulamanın ayarını değiştirmez. İlk sürümde yalnız log yalıtılmıştı;
son hash kontrolünde importun gerçek hafıza oturum tarihini yazdığı yakalandı ve
runner genişletildi. Bu ilk yan etki gizlenmedi/8of8finalhashPASS denmedi.
Önceden gözlenen ortak-log WinError32 sorunu bu çalışma
kapsamında üretim logger'ında değiştirilmedi.

Regresyonlar: onaysız yazma reddi; proje/tam yetki ayrımı; izin hatasında yetki
yükseltmeme; yazmalı retry yapmama; iç TypeError'da tek dispatch; sohbet writer
kilidi/checkpoint'i; tam yetki ve iç içe proje çakışması; başlangıç/checkpoint
hatalarında kilit temizliği; gerçek geçici klasörde önceki içeriğin arşivlenmesi;
Git dirty/untracked/deleted koruması; Git dışı arşiv; CRC/SHA; sınır/path reddi;
grup yazıcı→incelemeci sırası; yazıcı başarısızlığının gizlenmemesi.

İlk172 test geçti. Ek entegrasyon testinin ilk174 koşusunda sahte runtime'ın
TERMINAL kümesi eksik olduğundan test fixture'ı başarısız oldu; fixture düzeltildi.
Nihai test/paket sonucu aynı klasördeki teslim raporunda kaydedilir. Gerçek model
oturumu veya Warband görüşmesi yapılmış sayılmaz. Kamuya açık upload yapılmadı.

## Yedek ve teslim sınırı

Değişiklik öncesi dirty kaynak/test/docs yedeği:
`C:\Users\LENAVO\.codex\backups\quartz-permission-fix-20261020-101832.zip`.
Mevcut kullanıcı değişiklikleri resetlenmedi. `.env`/kullanıcı verileri kaynak
yedeğine katılmadı; paket değişimi yapılırsa eski dağıtım ayrıca bütün hâliyle
korunur ve JSON/.env dosyalarının hash eşitliği kontrol edilir.

İzleyen işler: Warband'a özel UM izin/yedek/proses profili, yerel IPC istemci
kimlik doğrulaması ve üretim log rotasyonunun çoklu-handle güvenliği. Bunlar
bu izin/checkpoint düzeltmesinin tamamlanmış kapsamı olarak gösterilmez.
