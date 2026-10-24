# Quartz kilit ekranı gözlem hatası — 23 Ekim 2026

## Gerçek kanıt

`labs/natural-desktop-20261022/evidence/8502e1a40cfd4ee6bade181a0fc5f293/` içindeki
ilk gözlem hedef test uygulamasını gösteriyor. `desktop_act` sonrasındaki ikinci PNG ise
Windows kilit ekranını gösteriyor; aynı gözlemin UIA ağacı hedef uygulamanın
`Durum: Düzeltildi` metnini içeriyor. Bu nedenle eski rapordaki
`OBSERVED UI CRITERION VERIFIED` ifadesi **görsel yeniden doğrulama kanıtı değildir**.

Fixture `callback.json` dosyasındaki `matches_reference=true` ve `action_count=1`,
test uygulamasının gerçekten bir kez düzeltildiğini destekler. Bu, kilit ekranı
görüntüsünü doğru hedef görüntüsü yapmaz; UIA ve görüntü aynı anda güvenilir
olarak eşleşmemiştir. Geçmiş kanıt silinmedi veya yeniden etiketlenmedi.

## Kök neden ve dar kapsamlı düzeltme

`NativeDesktopBackend.is_foreground` eski durumda foreground handle sıfırsa
görünür pencereyi, farklı masaüstü tespitinde yine görünür hedefi, ayrıca aynı
process/root-owner penceresini kabul edebiliyordu. Bu, uygulama UIA ağacı
okunabilirken ekran görüntüsünün Winlogon masaüstünden gelmesini engellemiyordu.

Yeni kaynak:

- Aktif input desktop adını hedef pencerenin desktop adıyla eşleştirir; eşleşme
  okunamıyorsa izin vermez.
- Foreground için yalnız tam hedef HWND veya onun gerçek child/root penceresini
  kabul eder; handle sıfır, aynı PID ve farklı masaüstü kestirmelerini kaldırır.
- Görüntü alma öncesinde masaüstünü, sonrasında masaüstü/foreground durumunu
  yeniden kontrol eder; değişim varsa gözlemi döndürmez.

`tests/test_desktop_broker.py` iki regresyon testi içerir. Hedefli 52 test ve
tam güvenli 331 test geçmiştir. Normal açık oturumda aktif masaüstü eşleştirmesi
salt-okunur kontrolde doğrulandı. Gerçek kilit ekranında yeni paketli uçtan uca
test **yapılmadı**; kullanıcı oturumunu kilitleme veya açık Quartz'ı kapatma
girişimi yapılmadı. Açık paket eski kodu çalıştırmaktadır; yeni kaynak, güvenli
dağıtıma kadar canlı düzeltme sayılmaz.
