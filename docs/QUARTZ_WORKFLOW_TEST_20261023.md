# Quartz daha büyük masaüstü testi — 23 Ekim 2026

## Sonuç ve kapsam

Gerçek Windows pencereleri kullanan, fakat paketli Quartz ana sohbetinin izin
kartını **kapsamayan** izole ürün testinde iki bağımsız iş akışı geçti. Üretim
Quartz kodu ve kurulu EXE değiştirilmedi. Bu sonuç, kullanıcının ana sohbetten
görev verip izin kartını onayladığı tam paketli kabulün yerine geçmez.

Test düzeni: `scripts/WorkflowFixture.cs` ile üç ayrı süreç/pencere. A'daki
hedef renk yalnız boyanmış ekranda; onaylı günlüğe ve UIA metnine yazılmıyor.
Codex görüntüyü okuyup onaylı B penceresinde doğru düğmeyi tek kez çağırıyor,
A'ya dönüp onarım hazır olduktan sonra son kontrolü tek kez yapıyor. Gemini
aynı anda yalnız proje günlüğünü izliyor. C ayrı, izin verilmemiş yem pencere.
Test işlemleri yalnız `labs/workflow-*` altında dosya oluşturur; ağ, Warband,
kullanıcı belgeleri ve korunan kayıtlara erişmez.

| Koşu | Gerçek UI sonucu | Callback | İzin sınırı | Kanıt |
|---|---|---|---|---|
| Sarı | Görsel hedef doğru okunup B→A tamamlandı | `choice_count=1`, `finish_count=1`, aynı nonce | C callback yok, C geçişi reddedildi | `labs/workflow-20261023-172939/acceptance.json`, `events.log` |
| Mavi | Farklı görsel hedefle aynı akış tamamlandı | `choice_count=1`, `finish_count=1`, aynı nonce | C callback yok, C geçişi reddedildi | `labs/workflow-20261023-173137/acceptance.json`, `events.log` |

İki koşuda da broker audit: A ve B'de birer başarılı UIA `invoke`, C'de sıfır
girdi. Fixture süreçleri test bitiminde kapatıldı. Gemini'nin log okumaları
ara aşamalarda güncel UI'den geride kaldı; ikinci koşunun son okuması B'deki
`correct_choice` ile A'daki `finalized` olaylarını doğruladı. Birinci koşuda
Gemini'nin son yorumunda kendi doğrulama kapsamı karışıktı; ham log ve callback
dosyaları kesin sonuç için esas alındı.

Önce güncel kodla mevcut piksel tabanlı üç pencere koşusu da çalıştırıldı:
`labs/multiwindow-codex-20261023-172357/acceptance.json`. A'da gerçek
`desktop_act(click)` audit'i oluştu fakat düğme callback'i hiç çalışmadı;
A/B/C sayaçları sıfır kaldı. Bu **FAILED — piksel hedefleme** olarak korundu.
Ardından aynı mevcut koşu taze UIA referanslarıyla geçti: A=1, B=1, C=0;
`labs/multiwindow-codex-20261023-172554/acceptance.json`. Piksel başarısızlığı
UIA başarısıyla silinmiş sayılmaz.

50 hedefli broker/çoklu pencere kaynak testi PASS. Yeni `scripts/workflow_acceptance.py`
fixture'ı derler, üç pencereyi açar, yalnız A/B için test kapsamı verir,
gerçek Codex/Gemini CLI ve Squad akışını çalıştırır, callback+audit+log'u
karşılaştırır ve yalnız kendi açtığı fixture süreçlerini kapatır. Bu test
harness'inin açık onayı, paketli Quartz sohbetindeki insan izin kartı değildir.

Ön değişiklik checkpoint'i:
`C:/Users/LENAVO/.codex/backups/quartz-bigger-test-20261023/agent-1792765692-bcdea026c6824e05ab3586fbd8146c8d.zip`.
Kurulu `dist/Quartz/Quartz.exe` hash'i önceki dağıtımla aynı:
`106A1A8E350BA34A21E6605CCB9EFC314A0A34AE38B869EBF77D4821CB4D9155`.

## Kalan gerçek kabul

Paketli Quartz'ın **ana sohbetinden** aynı A→B→A görevinin başlatılması,
sohbet içi gerçek kullanıcı onayı, iki pencerenin kapsamda görünmesi, Gemini
log kapsamı ve durdurma davranışı ayrıca canlı test edilmelidir. Bilgisayar
kullanımına dair izin kartını test operatörü kendi kendine onaylamaz. Bu nedenle
genel Quartz masaüstü kabulü henüz COMPLETE değildir.
