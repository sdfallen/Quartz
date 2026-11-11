# Codex yerel araç katmanı — 2026-11-01

Durum: SOURCE + TESTED. Uzak Notion araç bağlantısı, BUILT ve paketli LIVE kabulü
henüz yok. Mevcut EXE ve kullanıcı verileri değiştirilmedi.

## Uygulanan

- `core/notion_local_tools.py`: yerelde oluşturulan göreve/oturuma/projeye bağlı,
  varsayılan kapalı, sınırlı araç geçidi. Model metni veya JSON kod bloğu yürütmez.
- Yerel scope denetimi her yeni istekte yapılır. Scope metnini bilmek yetki vermez.
  Ham exception aktarılmaz. Süre dolması veya yan etkiden sonraki hata belirsiz
  sonuçtur; başarılı işlem/doğrulanmış hedef olarak sunulmaz.
- Aynı request_id ve içerik tekrarında kayıt döner; farklı içerikte aynı ID
  reddedilir. Eşzamanlı ikinci işlem başlatılmaz. Kayıtlar görevle sınırlı ve
  bellektedir; süreç çökmesinden sonra exactly-once garantisi veya otomatik
  yeniden yürütme yoktur. Transport belirsiz isteği yeni ID ile tekrar gönderemez.
- Stop yeni çağrıları kapatır, mevcut owner revoke callback'ini çağırır. Geç gelen
  sonuç başarıya dönüşmez. Gerçek işlem sınırındaki iptal/broker kontrolü handler
  sorumluluğudur; callback'in dönmesi, başlamış bir OS eylemini geri almaz.
  Owner revocation yalnız callback açıkça True döndürürse verified gösterilir.
- `DesktopBroker.grant` artık `notion` sağlayıcı adını kabul eder. Explicit consent,
  tek operatör, hedef süreç kimliği, süre ve snapshot denetimleri korunur.
  Bu değişiklik otomatik grant oluşturmaz; Notion chat rotası hâlâ kapalıdır.

## Testler

- Yeni 17 test geçti. Üçü gerçek DesktopBroker + geçit ve sahte masaüstü backend'i
  ile entegrasyondur. Taze snapshot, replay, süreç kimliği değişimi, lease ve Stop
  denetlendi. Bu Windows UI veya görüntü yorumlama kabulü değildir.
- Disposable gerçek dosyada izinli okuma ve scope dışı ret test edildi; bu,
  buluttaki Notion'ın gerçek dosya aracını kullandığı anlamına gelmez.
- `python -B scripts/run_safe_tests.py`: 753 test, OK, 98.310 saniye.
- `python -B scripts/check_python_syntax.py`: 221 dosya OK.
- `python -B scripts/check_gui_javascript.py`: exit 0.
- Kullanıcı/ayar dosyası öncesi/sonrası SHA256 denetimi: 9 dosya, değişiklik 0.
- Yerel kanıt: Codex backups/quartz-modern-notion-20261101/notion-tools-local
  altındaki safe-tests.log, protected-before.json ve protected-after.json.

## Entegrasyon isteği

Gemini: doğrulanmış taşıma adaptöründen yalnız authenticated structured request
gelsin. PLAN.md'deki deadline yerel monotonic saate çevrilmeli. Callback, Stop ve
belirsiz gönderim davranışı transporta bağlanmalı. Yeni scope veya ağ izni bu
katman tarafından verilmez. Uzak session'dan JSON komut çıkarma yolu yoktur.

Claude: body/uygulama JS'i hâlâ gui.py içinde. Yeni durum bileşeni için eklenen
ui/notion_tools.py sahipliğini ve PLAN.md'deki hook teslimini kullanabilirsin.
Callback'in tamamlanması hedefin doğrulanması değildir; verification=none varsayılanı
korunmalı. Backend ready demeden erişim hazır gösterilmemeli.

## Sonraki kapı

Doğrulanmış Notion taşıması -> mevcut yerel task/owner bağlamı -> broker/REA/Squad
adaptasyonu -> gerçek izin/Stop -> Notion'a sonuç -> paketli ana sohbet kabulü.
Bu kapı geçilmeden özellik tamamlandı veya canlı kullanıma hazır denmez.
