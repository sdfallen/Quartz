# Connecting açılış hatası — 28 Ekim 2026

## Kanıtlanan neden

GUI'nin düşük donanım polling değişikliğinde `desktopTaskState.active` kullanılmış, fakat böyle bir değişken tanımlı değil. Mevcut gerçek arayüz durumu `desktopView` içinde tutuluyor.

Boşta açılışta `pollPing()` daha try bloğuna gelmeden `isUiIdle()` çağırıyor. Bu çağrı `ReferenceError: desktopTaskState is not defined` ile kesiliyor; backend health isteği ve sonraki timer kurulmadan fonksiyon çıkıyor. Sonuç: backend dinlediği hâlde üst yazı CONNECTING, Squad arka plan bilgisi de yenilenmiyor.

Canlı eski pencerenin UIA ağacında CONNECTING ve “Squad: Kontrol ediliyor” görüldü. RGL yerine uygulamanın assistant.log dosyasında chat_status/tasks istekleri var, tekrarlanan health istekleri yoktu.

## Düzeltme

- `hasActiveDesktopTask()` mevcut `desktopView.stop_ref` üzerinden görev durumunu okur. Hatalı üç referans kaldırıldı.
- Bağlantı polling'inin ilk hesaplaması try içine alındı.
- Hata hâlinde gösterge ÇEVRİMDIŞI olur; timer finally içinde yeniden kurulur.
- Düşük donanım için mevcut idle/hidden polling aralıkları korundu. Yetki/kimlik doğrulama ve model bağlantıları değişmedi.

## Doğrulama

- `tests/test_gui_connection_polling.py`, uygulamanın gerçek gömülü JS fonksiyonlarını Node içinde çalıştırır: ilk online durum, başarısız ping, yeniden deneme timer'ı, normal idle, aktif masaüstü görevi ve olay polling'i.
- Önce test gerçek ReferenceError ile FAILED; düzeltmeden sonra PASS.
- Gömülü JS sözdizimi PASS.
- Tam regresyon: **508/508 PASS** (`regression.log`).
- Ön kaynak kopyası ve test kanıtları `C:\Users\LENAVO\.codex\backups\quartz-connecting-20261028` altında. Son paket/canlı durum aynı klasördeki teslim makbuzu ve UIA kanıtıyla ayrıca kaydedilir.

Önceki sözdizimi ve Python testleri bu tanımsız JS globalini yakalamıyordu. Yeni test yalnız parse etmek yerine gerçek polling döngülerini yürütür.

## Canlı teslim

Kurulu EXE SHA256: `3ef70a10f43abe123e6621d85c28ee45ac2cb4579ccf60520428c7a148832026`.

Boşta olan eski uygulama normal Alt+F4 ile kapatıldı. Yedekli dağıtım sonrası yeni süreç PID 19148, 18:44'te açıldı. `live-uia.txt` gerçek pencerede **ÇEVRİMİÇİ** yazısını ve Tam Yetki durumunu gösterir. `live-health.txt` tekrarlanan gerçek health isteklerini kaydeder. Olay/sohbet polling'i de yeniden çalışmaktadır. Bu kabul backend bağlantısı ve UI durum yenilemesi kapsamındadır; model görevi kabulü değildir.

`deployment-receipt.json`: kullanıcı verilerinin tümü eşit kopyalandı. Önceki dağıtım `quartz-before-desktop-bridge-20261028-184354` yedeğinde korunur. Kaynak/kurulumdaki dokuz korunan veri dosyası `data-after.json` ile ayrıca karşılaştırıldı.
