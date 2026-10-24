# Quartz masaüstü yürütücüsü

Quartz artık Windows UI Automation üzerinden pencereleri ve arayüz öğelerini okuyabilir.
Model `desktop_windows` ile pencereyi, `desktop_inspect` ile düğme/metin alanını seçer.
`desktop_action` gözlenen öğeye işlem uygular ve işlemden sonraki yeni arayüzü döndürür.
Bir sonraki eylem bu yeni gözlemi kullanır. Görev tamamlandı kararı, istenen sonuç ile
gözlenen durum karşılaştırılarak verilmelidir.

Desteklenen öğe eylemleri: invoke, select, expand, collapse, toggle, set_text.
Metin girişi Unicode destekleyen Edit öğelerinde doğrudan yapılır. Pencere veya öğe
değişirse eski kimlikler reddedilir. Gözlem kimlikleri iki dakika sonra geçersizleşir
ve bir eylem için bir kez kullanılabilir. Şifre alanları arayüz dökümüne alınmaz.

Örnek görevler:

- “Not Defteri'ni aç ve bir alışveriş listesi yaz.”
- “Şimdi başlığı değiştir.”
- “Dosya Gezgini'nde İndirilenler klasörünü aç.”
- “Steam'i aç”, ardından “Kütüphaneme gir”.
- “Açık pencereleri göster.”

Araçlar mevcut onay ve Güvenli Mod sistemine bağlıdır. İptal düğmesi sonraki
adımları durdurur; çalışan harici bir API isteğinin anında kesilmesini garanti etmez.
Bir mesajda en fazla 20 araç turu yürütülür; ardından devam mesajı verilebilir.

Kapsam: normal kullanıcı oturumunda erişilebilirlik öğeleri sunan Windows
uygulamaları. Her uygulama aynı düzeyde destek vermez: oyunların özel çizilen
arayüzleri, kilit ekranı, UAC ve daha yüksek yetkide çalışan pencereler genel UIA
yoluyla yönetilemeyebilir. Bu durumlarda Quartz somut engeli bildirmelidir.
Görsel analiz için mevcut pencere görüntüsü araçları, Steam ve dosya işlemleri
için özel araçlar kullanılmaya devam eder. Ekran Rehberi yalnızca hedef pencere
öndeyken görüntü alır; kendi başına pencere odağını değiştirmez.

Öğrenme mevcut başarılı araç akışlarını hatırlamaktır; modelin kendisini yeniden
eğitmesi anlamına gelmez. Eski arayüz kimlikleri öğrenilmiş akışlardan tekrar
kullanılmamalıdır.

Doğrulama: `python -m unittest discover -s tests -q`.
UIA bağımlılığı: pywinauto 0.6.9. Build betiği bu bağımlılığı paketler ve yerel
dist/Quartz kullanıcı verilerini yeniden derlemeden önce yedekleyip geri yükler.

12 Eylül 2026: 76 yerel test geçti; gerçek masaüstünde pencere ve kontrol okuma
denendi. Canlı modelle eylem zinciri henüz doğrulanmadı: GitHub 410, eski NVIDIA
modeli 410, güncel NVIDIA modelleri mevcut anahtarla 403 döndürdü. Sağlayıcı NVIDIA,
model nvidia/nemotron-3-super-120b-a12b olarak ayarlandı; geçerli erişim gerektirir.
`python scripts/probe_nvidia.py nvidia/nemotron-3-super-120b-a12b` sohbet, zorunlu
araç çağrısı ve yapay araç sonucuyla devam yanıtını test eder; masaüstünde işlem yapmaz.

# CLI agent desktop bridge

The separate Codex/Gemini operator slice and its live acceptance are documented
in [DESKTOP_AGENT_BRIDGE_20261020.md](docs/DESKTOP_AGENT_BRIDGE_20261020.md) and
[DESKTOP_LIVE_TEST_20261020.md](docs/DESKTOP_LIVE_TEST_20261020.md). Classic UIA
Edit/Invoke passed. The subsequent [pixel input repair](docs/DESKTOP_PIXEL_FIX_20261021.md)
also passed real coordinate-click/Space tests in a local WebView with both CLI
providers. This is still bounded-window control, not universal app/Warband support.

21 October: [packaged acceptance and simpler chat](docs/QUARTZ_ACCEPTANCE_AND_CHAT_STYLE_20261021.md)
records the blocked GUI observation, authenticated local IPC and the persistent
Yanıt Ayrıntısı preference. Source development should start with
`python quartz_entry.py` so GUI/backend share the same process-local capability.

21 October multiwindow update: the CLI bridge now supports task-bound sets of
approved HWNDs and narrow single-use EXE launches. Its broker uses **15-second**
one-use snapshots, distinct from the legacy two-minute UIA references above.
Main-chat consent selects multiple windows in one card; the observer remains
log-only. See [multiwindow implementation and acceptance](docs/QUARTZ_MULTIWINDOW_20261021.md).
New HWNDs/descendants are not automatically trusted; Warband remains excluded
until the dedicated Universal Modder protection adapter exists.
