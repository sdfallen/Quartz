# Odak değişiminde görevin sürmesi

Tarih: 4 Kasım 2026. Sahip: Claude. Taban: `4120f5e`. Kullanıcı isteği: pencere
değişimi veya kullanıcı müdahalesi görevi bitirmesin; görev İptal'e kadar sürsün.

## Gözlenen hata

Kanıt: `task-evidence/9e03d429…` ve `2b341d29…`, sonuç
`blocked: foreground changed (user takeover)`. Her iki Aseprite görevi seçili
`aster-warband` projesinde çalıştı. `persistent_control=not self.warband` bu
profilde odak kurtarmayı kapattığı için oyun dışı pencerede de görev durdu.

## Değişiklik

- `core/natural_desktop.py`: odak kurtarma yalnız Warband profilindeki oyun
  penceresinde kapalı. Devam talimatı yalnız Warband metninde kaldığı için genel
  talimata taşındı; "engeli raporla" ifadesi kaldırıldı.
- `core/desktop_broker.py`: kalıcı kontrolde başarısız `desktop_switch` görevi
  bitirmez; girdi göndermeden hata döner.
- `core/desktop_agents.py`: eski giriş yolunun talimatı aynı sözleşmeye geçti.

Warband oyun girdisi, Stop, kilit ekranı, süreç kimliği, taze gözlem ve UAC
sınırları değişmedi. Odak değişiminden sonra eski eylem tekrar uygulanmaz.

## Bilinçli olarak korunan sınırlar

Görev süresi (`expires_at`), oturum başına 100 eylem bütçesi, kapatılan veya
süreci değişen hedef pencere görevi hâlâ bitirir. Ajan kendi turunu bitirirse
görev de biter; talimat bunu odak nedeniyle yapmamasını söyler ama zorlamaz.

## Kanıt seviyesi

TESTED: yeni regresyonlar düzeltmesiz kodda başarısız, düzeltmeyle başarılı.
Gerçek Windows odak değişimi ve paketli sohbet kabulü bu belgede kanıtlanmaz.
